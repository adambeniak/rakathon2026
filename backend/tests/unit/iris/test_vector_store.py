from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest

from app.iris.db import DbConnection, IrisPool
from app.iris.vector_store import (
    DELETE_DOC_SQL,
    INSERT_SQL,
    ChunkRow,
    VectorStore,
    as_of_params,
    hit_from_row,
    search_sql,
    text_search_sql,
    vector_literal,
)

AS_OF = datetime(2026, 10, 21, 8, 0, tzinfo=timezone(timedelta(hours=2)))


class RecordingCursor:
    def __init__(self, calls: list[tuple[str, Any]], rows: Sequence[Sequence[Any]]) -> None:
        self.calls = calls
        self.rows = rows

    def execute(self, operation: str, params: Sequence[Any] = ()) -> None:
        self.calls.append((operation, list(params)))

    def executemany(self, operation: str, seq_of_params: Sequence[Sequence[Any]]) -> None:
        self.calls.append((operation, [list(p) for p in seq_of_params]))

    def fetchone(self) -> Sequence[Any] | None:
        return (3,)

    def fetchall(self) -> Sequence[Sequence[Any]]:
        return self.rows

    def close(self) -> None:
        pass


class RecordingConnection:
    def __init__(self, calls: list[tuple[str, Any]], rows: Sequence[Sequence[Any]]) -> None:
        self.calls = calls
        self.rows = rows

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self.calls, self.rows)

    def commit(self) -> None:
        self.calls.append(("COMMIT", None))

    def rollback(self) -> None:
        self.calls.append(("ROLLBACK", None))

    def close(self) -> None:
        pass


def make_store(rows: Sequence[Sequence[Any]] = ()) -> tuple[VectorStore, list[tuple[str, Any]]]:
    calls: list[tuple[str, Any]] = []

    def connect() -> DbConnection:
        return RecordingConnection(calls, rows)

    return VectorStore(IrisPool(connect, max_size=1), dim=3), calls


def row(seq: int, doc_ref: str = "DocumentReference/9") -> ChunkRow:
    return ChunkRow(
        doc_ref=doc_ref,
        doc_id="09_Biopsie_vykon_KOC2_2026-10-12",
        patient_ref="Patient/1",
        seq=seq,
        title="EUS-FNB",
        authored_on=date(2026, 10, 12),
        received_at=datetime(2026, 10, 12, 13, 0, tzinfo=timezone(timedelta(hours=2))),
        text=f"chunk {seq}",
        char_start=seq * 10,
        char_end=seq * 10 + 7,
        embedding=[0.1, 0.2, 0.3],
        model="m",
    )


def test_as_of_params_mirror_doc_included() -> None:
    # Authored strictly before the Prague as_of day; received up to the as_of instant, in UTC.
    assert as_of_params(AS_OF) == ("2026-10-21", "2026-10-21 06:00:00.000000")


def test_as_of_params_use_prague_day_for_utc_input() -> None:
    late_utc = datetime(2026, 10, 20, 23, 30, tzinfo=UTC)  # already 21. 10. 01:30 in Prague
    assert as_of_params(late_utc) == ("2026-10-21", "2026-10-20 23:30:00.000000")


def test_as_of_params_refuse_naive() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        as_of_params(datetime(2026, 10, 21, 8, 0))  # noqa: DTZ001 - the point of the test


def test_both_legs_share_the_scope_filter() -> None:
    scope = "WHERE PatientRef = ? AND EmbeddingModel = ? AND AuthoredOn < ? AND ReceivedOn <= ?"
    vector, text = search_sql(8), text_search_sql(30)
    assert vector.startswith("SELECT TOP 8 %ID, ")
    assert scope in vector
    assert vector.endswith("ORDER BY Score DESC")
    assert text.startswith("SELECT TOP 30 %ID, ")
    assert text.endswith(
        f"{scope} AND (%ID %FIND search_index(DocChunkText, ?, 0) OR %ID %FIND search_index(DocChunkTitle, ?, 0))"
    )
    with pytest.raises(ValueError, match="between"):
        search_sql(0)


def test_vector_literal_checks_dimensions() -> None:
    assert vector_literal([1, 0.5, -2], 3) == "[1.0,0.5,-2.0]"
    with pytest.raises(ValueError, match="expects 3"):
        vector_literal([1.0], 3)


def test_replace_document_deletes_then_inserts_in_one_transaction() -> None:
    store, calls = make_store()

    assert store.replace_document("DocumentReference/9", [row(0), row(1)]) == 2

    assert [c[0] for c in calls] == [DELETE_DOC_SQL, INSERT_SQL, "COMMIT"]
    inserted = calls[1][1]
    assert inserted[0][:7] == [
        "DocumentReference/9",
        "09_Biopsie_vykon_KOC2_2026-10-12",
        "Patient/1",
        0,
        "EUS-FNB",
        "2026-10-12",
        "2026-10-12 11:00:00.000000",  # stored in UTC, full precision
    ]
    assert inserted[1][-1] == "[0.1,0.2,0.3]"


def test_replace_document_refuses_foreign_rows() -> None:
    store, _ = make_store()
    with pytest.raises(ValueError, match="doc_ref"):
        store.replace_document("DocumentReference/9", [row(0, doc_ref="DocumentReference/8")])


def test_search_binds_vector_patient_model_and_as_of() -> None:
    db_row = (7, "DocumentReference/9", "09_x", "EUS", 1, "2026-10-12", "2026-10-12 11:00:00", "t", 5, 9, 0.81)
    store, calls = make_store([db_row])

    hits = store.search(patient_ref="Patient/1", vector=[1.0, 0.0, 0.0], as_of=AS_OF, k=8, model="m")

    assert calls[0][1] == ["[1.0,0.0,0.0]", "Patient/1", "m", "2026-10-21", "2026-10-21 06:00:00.000000"]
    assert hits[0].received_at == datetime(2026, 10, 12, 11, 0, tzinfo=UTC)
    assert hits[0].authored_on == date(2026, 10, 12)
    assert hits[0].score == pytest.approx(0.81)
    assert hits[0].row_id == 7


def test_text_search_binds_the_query_last() -> None:
    store, calls = make_store([])
    store.text_search(patient_ref="Patient/1", query="vysaz* OR biop*", as_of=AS_OF, k=30, model="m")
    query = "vysaz* OR biop*"
    assert calls[0][1] == ["Patient/1", "m", "2026-10-21", "2026-10-21 06:00:00.000000", query, query]


def test_hit_from_row_accepts_driver_types() -> None:
    hit = hit_from_row(
        (1, "DocumentReference/9", "09_x", None, 0, date(2026, 10, 12), datetime(2026, 10, 12, 11, 0), "t", 0, 1, 0.5)  # noqa: DTZ001 - driver returns naive UTC
    )
    assert hit.title == "09_x"
    assert hit.received_at.tzinfo is UTC


def test_sub_second_receipts_are_not_truncated() -> None:
    # Truncation would store 06:00:00.9 and an as_of of 06:00:00.1 both as 06:00:00 and let the later document in.
    received = datetime(2026, 10, 21, 6, 0, 0, 900000, tzinfo=UTC)
    as_of = datetime(2026, 10, 21, 6, 0, 0, 100000, tzinfo=UTC)
    from app.iris.vector_store import utc_timestamp

    assert utc_timestamp(received) == "2026-10-21 06:00:00.900000"
    assert as_of_params(as_of)[1] == "2026-10-21 06:00:00.100000"
    assert as_of_params(as_of)[1] < utc_timestamp(received)


class FailingCursor(RecordingCursor):
    def __init__(self, error: Exception) -> None:
        super().__init__([], [])
        self.error = error

    def execute(self, operation: str, params: Sequence[Any] = ()) -> None:
        raise self.error


@pytest.mark.parametrize("error_name", ["dbapi", "oserror"])
def test_infrastructure_failures_become_vector_store_unavailable(error_name: str) -> None:
    import iris.dbapi

    from app.iris.vector_store import VectorStoreUnavailableError

    error: Exception = iris.dbapi.OperationalError("down") if error_name == "dbapi" else ConnectionResetError()

    class Conn(RecordingConnection):
        def cursor(self) -> FailingCursor:  # type: ignore[override]
            return FailingCursor(error)

    store = VectorStore(IrisPool(lambda: Conn([], []), max_size=1), dim=3)
    with pytest.raises(VectorStoreUnavailableError):
        store.search(patient_ref="Patient/1", vector=[1.0, 0.0, 0.0], as_of=AS_OF, k=8, model="m")


def test_programming_errors_are_not_masked() -> None:
    class Conn(RecordingConnection):
        def cursor(self) -> FailingCursor:  # type: ignore[override]
            return FailingCursor(TypeError("bug"))

    store = VectorStore(IrisPool(lambda: Conn([], []), max_size=1), dim=3)
    with pytest.raises(TypeError):
        store.text_search(patient_ref="Patient/1", query="a*", as_of=AS_OF, k=8, model="m")
