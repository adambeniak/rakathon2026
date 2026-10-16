from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any

import pytest

from app.iris.db import DbConnection, IrisPool, PoolClosedError, PoolExhaustedError


class FakeCursor:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def execute(self, operation: str, params: Sequence[Any] = ()) -> None:
        if operation == "FAIL":
            raise RuntimeError("sql error")
        self.log.append(f"execute {operation}")

    def fetchone(self) -> Sequence[Any] | None:
        return (1,)

    def fetchall(self) -> Sequence[Sequence[Any]]:
        return [(1,)]

    def close(self) -> None:
        self.log.append("cursor.close")


class FakeConnection:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.log)

    def commit(self) -> None:
        pass

    def close(self) -> None:
        self.log.append("connection.close")


@pytest.fixture
def log() -> list[str]:
    return []


@pytest.fixture
def opened(log: list[str]) -> list[FakeConnection]:
    return []


@pytest.fixture
def pool(log: list[str], opened: list[FakeConnection]) -> IrisPool:
    def connect() -> DbConnection:
        conn = FakeConnection(log)
        opened.append(conn)
        return conn

    return IrisPool(connect, max_size=3, acquire_timeout_s=0.05)


def test_size_is_capped_at_three() -> None:
    with pytest.raises(ValueError, match="between 1 and 3"):
        IrisPool(lambda: FakeConnection([]), max_size=4)


def test_cursor_closed_and_connection_reused(pool: IrisPool, log: list[str], opened: list[FakeConnection]) -> None:
    pool.ping()
    pool.ping()

    assert len(opened) == 1
    assert log == ["execute SELECT 1", "cursor.close", "execute SELECT 1", "cursor.close"]


def test_error_closes_cursor_then_discards_connection(
    pool: IrisPool, log: list[str], opened: list[FakeConnection]
) -> None:
    with pytest.raises(RuntimeError), pool.cursor() as cur:
        cur.execute("FAIL")

    assert log == ["cursor.close", "connection.close"]
    pool.ping()
    assert len(opened) == 2


def test_exhausted_pool_times_out(pool: IrisPool) -> None:
    release = threading.Event()
    holding = threading.Barrier(4)

    def hold() -> None:
        with pool.connection():
            holding.wait()
            release.wait(timeout=2)

    threads = [threading.Thread(target=hold) for _ in range(3)]
    for t in threads:
        t.start()
    holding.wait()
    try:
        with pytest.raises(PoolExhaustedError), pool.connection():
            pass
    finally:
        release.set()
        for t in threads:
            t.join()


def test_close_all_closes_idle_and_refuses_new_work(pool: IrisPool, log: list[str]) -> None:
    pool.ping()
    pool.close_all()

    assert log[-1] == "connection.close"
    with pytest.raises(PoolClosedError):
        pool.ping()
