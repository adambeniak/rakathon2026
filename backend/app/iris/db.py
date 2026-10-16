"""Tiny bounded DB-API connection pool for IRIS SQL (owner: P1).

IRIS community edition allows 8 connections in total, so the backend never holds more than 3 (`IRIS_POOL_SIZE`).
The driver is synchronous: call pool methods from async code via `asyncio.to_thread`.

    with pool.cursor() as cur:            # cursor is always closed first,
        cur.execute("SELECT TOP 5 …", [x])  # then the connection goes back to the pool,
        rows = cur.fetchall()               # or is closed and discarded if anything failed.

    with pool.transaction() as cur:       # autocommit off: commit on success, rollback on any error
        cur.execute("DELETE …", [x])
        cur.executemany("INSERT …", rows)
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Protocol

import structlog

from app.settings import Settings

log = structlog.get_logger(__name__)

MAX_POOL_SIZE = 3


class DbCursor(Protocol):
    def execute(self, operation: str, params: Sequence[Any] = ...) -> Any: ...
    def executemany(self, operation: str, seq_of_params: Sequence[Sequence[Any]]) -> Any: ...
    def fetchone(self) -> Sequence[Any] | None: ...
    def fetchall(self) -> Sequence[Sequence[Any]]: ...
    def close(self) -> None: ...


class DbConnection(Protocol):
    def cursor(self) -> DbCursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


class PoolExhaustedError(RuntimeError):
    """All connections are busy for longer than the acquire timeout."""


class PoolClosedError(RuntimeError):
    """The pool was closed (application shutdown)."""


class IrisPool:
    def __init__(
        self,
        connect: Callable[[], DbConnection],
        *,
        max_size: int = MAX_POOL_SIZE,
        acquire_timeout_s: float = 10.0,
    ) -> None:
        if not 1 <= max_size <= MAX_POOL_SIZE:
            raise ValueError(f"max_size must be between 1 and {MAX_POOL_SIZE}")
        self._connect = connect
        self._idle: queue.LifoQueue[DbConnection] = queue.LifoQueue()
        self._slots = threading.BoundedSemaphore(max_size)
        self._acquire_timeout_s = acquire_timeout_s
        self._closed = False

    @classmethod
    def from_settings(cls, settings: Settings) -> IrisPool:
        def connect() -> DbConnection:
            import iris

            connection: DbConnection = iris.connect(
                settings.iris_host,
                settings.iris_superserver_port,
                settings.iris_namespace,
                settings.iris_user,
                settings.iris_password.get_secret_value(),
            )
            return connection

        return cls(connect, max_size=settings.iris_pool_size)

    @contextmanager
    def connection(self) -> Iterator[DbConnection]:
        if self._closed:
            raise PoolClosedError("IRIS pool is closed")
        if not self._slots.acquire(timeout=self._acquire_timeout_s):
            raise PoolExhaustedError(f"no IRIS connection free within {self._acquire_timeout_s} s")
        conn: DbConnection | None = None
        healthy = False
        try:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                conn = self._connect()
            yield conn
            healthy = True
        finally:
            if conn is not None:
                if healthy and not self._closed:
                    self._idle.put(conn)
                else:
                    _close(conn)
            self._slots.release()

    @contextmanager
    def cursor(self) -> Iterator[DbCursor]:
        with self.connection() as conn:
            cur = conn.cursor()
            try:
                yield cur
            finally:
                cur.close()

    @contextmanager
    def transaction(self) -> Iterator[DbCursor]:
        """One connection with autocommit off (the driver default is on): commit on success, rollback on error.

        After an error the connection is discarded by `connection()`, so autocommit is restored only on success.
        """
        with self.connection() as conn:
            set_autocommit: Callable[[bool], None] | None = getattr(conn, "setAutoCommit", None)
            if set_autocommit is not None:
                set_autocommit(False)
            cur = conn.cursor()
            try:
                yield cur
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                cur.close()
            if set_autocommit is not None:
                set_autocommit(True)

    def ping(self) -> None:
        """Round-trip `SELECT 1`; raises on any failure."""
        with self.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

    def close_all(self) -> None:
        self._closed = True
        while True:
            try:
                _close(self._idle.get_nowait())
            except queue.Empty:
                return


def _close(conn: DbConnection) -> None:
    try:
        conn.close()
    except Exception as exc:  # noqa: BLE001 - a broken connection may fail to close; it is discarded either way
        log.warning("iris_connection_close_failed", error_type=type(exc).__name__)
