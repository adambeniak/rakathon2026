"""Idempotent bootstrap of an InterSystems IRIS for Health container for Štafeta.

Works against a local docker container or the team's Azure Container Instance (no shell needed):
  1. waits until the superserver (1972) and web server (52773) answer,
  2. creates the FHIRSERVER namespace (HS.Util.Installer.Foundation) if missing,
  3. installs a FHIR R4 endpoint (JsonAdvSQL strategy) if missing,
  4. creates (or migrates) the vector-search table for document chunks (+ HNSW index when supported),
  5. prints the IRIS version and the FHIR CapabilityStatement status.

Adapted from intersystems-community/FHIR-AI-Hackathon-Kit (docker-iris-fhir/fhir_server_setup_native.py).
Re-run after every ACI restart: storage there is NOT persistent.

Usage:
  make iris-bootstrap   (= uv run --env-file .env --with intersystems-irispython==5.4.1 python scripts/bootstrap_iris.py)
Env: IRIS_HOST, IRIS_SUPERSERVER_PORT, IRIS_WEB_PORT, IRIS_USER, IRIS_PASSWORD, IRIS_NAMESPACE,
     FHIR_ENDPOINT (default /fhir/r4), EMBEDDING_DIM (default 384).
"""

from __future__ import annotations

import base64
import os
import sys
import time
import urllib.error
import urllib.request

import iris  # intersystems-irispython

HOST = os.environ.get("IRIS_HOST", "localhost")
PORT = int(os.environ.get("IRIS_SUPERSERVER_PORT", "1972"))
WEB_PORT = int(os.environ.get("IRIS_WEB_PORT", "52773"))
USER = os.environ.get("IRIS_USER", "_SYSTEM")
PASSWORD = os.environ.get("IRIS_PASSWORD") or sys.exit("Set IRIS_PASSWORD")
NAMESPACE = os.environ.get("IRIS_NAMESPACE", "FHIRSERVER")
ENDPOINT = os.environ.get("FHIR_ENDPOINT", "/fhir/r4")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "384"))
STRATEGY = "HS.FHIRServer.Storage.JsonAdvSQL.InteractionsStrategy"
METADATA = "hl7.fhir.r4.core@4.0.1"


def native(namespace: str):
    conn = iris.createConnection(HOST, PORT, namespace, USER, PASSWORD)
    return conn, iris.createIRIS(conn)


def wait_ready(timeout_s: int = 600) -> None:
    """Wait for the superserver (1972) and the web server (52773). Fail fast on wrong credentials."""
    deadline = time.time() + timeout_s
    while True:
        try:
            conn, irispy = native("%SYS")
            version = irispy.classMethodString("%SYSTEM.Version", "GetVersion")
            conn.close()
            print(f"IRIS superserver ready: {version}")
            break
        except Exception as exc:  # noqa: BLE001 - startup produces many transient errors
            msg = str(exc)
            if "Access Denied" in msg or "password" in msg.lower() or "authentication" in msg.lower():
                raise SystemExit(f"IRIS rejected the credentials ({msg}). Check IRIS_USER / IRIS_PASSWORD.") from exc
            if time.time() > deadline:
                raise SystemExit(f"IRIS not ready after {timeout_s}s: {msg}") from exc
            print(f"waiting for IRIS superserver at {HOST}:{PORT} ... ({msg[:120]})")
            time.sleep(10)
    url = f"http://{HOST}:{WEB_PORT}/csp/sys/UtilHome.csp"
    while True:
        try:
            urllib.request.urlopen(url, timeout=10)
            print("IRIS web server ready")
            return
        except urllib.error.HTTPError:
            print("IRIS web server ready (answered with an HTTP error, which is fine)")
            return
        except (urllib.error.URLError, OSError) as exc:
            if time.time() > deadline:
                raise SystemExit(f"IRIS web server not reachable at {url}: {exc}") from exc
            print(f"waiting for IRIS web server at {url} ... ({exc})")
            time.sleep(10)


def ensure_namespace_and_fhir() -> None:
    conn, irispy = native("HSLIB")
    try:
        if not irispy.classMethodBoolean("%SYS.Namespace", "Exists", NAMESPACE):
            print(f"creating namespace {NAMESPACE} (takes a few minutes) ...")
            irispy.classMethodVoid("HS.Util.Installer.Foundation", "Install", NAMESPACE)
        else:
            print(f"namespace {NAMESPACE} exists")
    finally:
        conn.close()

    conn, irispy = native(NAMESPACE)
    try:
        if irispy.classMethodBoolean("HS.FHIRServer.ServiceInstance", "ExistsByUrl", ENDPOINT):
            print(f"FHIR endpoint {ENDPOINT} exists")
            return
        print(f"installing FHIR endpoint {ENDPOINT} (takes a few minutes) ...")
        irispy.classMethodVoid("HS.FHIRServer.Installer", "InstallNamespace")
        irispy.classMethodVoid("HS.FHIRServer.Installer", "InstallInstance", ENDPOINT, STRATEGY, METADATA)
    finally:
        conn.close()


# Columns added after the first release of the table: (name, DDL type). `ensure_vector_table` adds any that are missing.
DOC_CHUNK_EXTRA_COLUMNS = (
    ("DocId", "VARCHAR(100)"),  # business id of the source document (DocumentReference.identifier), cited by /ask
    ("Title", "VARCHAR(500)"),
    ("CharStart", "INTEGER"),  # chunk = normalised document text [CharStart, CharEnd)
    ("CharEnd", "INTEGER"),
    ("EmbeddingModel", "VARCHAR(200)"),  # query and stored vectors must come from the same model
)
DOC_CHUNK_INDEXES = (
    ("DocChunkPatient", "(PatientRef)"),
    ("DocChunkDocRef", "(DocRef)"),
    ("DocChunkHNSW", "(Embedding) AS HNSW(Distance='Cosine')"),
    # Full-text leg of hybrid search. No INDEXOPTION: IRIS has no Czech stemmer (stemming crashes on insert);
    # the backend sends prefix wildcards ("vysaz*") instead.
    ("DocChunkText", "(Text) AS %iFind.Index.Basic(LANGUAGE='cs', LOWER=1)"),
    # Titles carry words the text may lack (report 11 never says "histologie" except in its title).
    ("DocChunkTitle", "(Title) AS %iFind.Index.Basic(LANGUAGE='cs', LOWER=1)"),
)
OPTIONAL_INDEXES = ("DocChunkHNSW", "DocChunkText", "DocChunkTitle")  # search still works without them (exact / vector-only)


def ensure_vector_table() -> None:
    """Stafeta.DocChunk: one row per chunk. ReceivedOn is stored in UTC, AuthoredOn is the authored date.

    Idempotent: creates the table, adds missing columns to an older table and creates missing indexes.
    """
    conn = iris.connect(HOST, PORT, NAMESPACE, USER, PASSWORD)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'Stafeta' AND TABLE_NAME = 'DocChunk'"
        )
        if cur.fetchone()[0]:
            print("table Stafeta.DocChunk exists")
        else:
            extra = "".join(f",\n                    {name} {ddl}" for name, ddl in DOC_CHUNK_EXTRA_COLUMNS)
            cur.execute(
                f"""CREATE TABLE Stafeta.DocChunk (
                    DocRef VARCHAR(200) NOT NULL,
                    PatientRef VARCHAR(200),
                    Seq INTEGER NOT NULL,
                    AuthoredOn DATE,
                    ReceivedOn TIMESTAMP,
                    Text VARCHAR(32000),
                    Embedding VECTOR(DOUBLE, {EMBEDDING_DIM}){extra}
                )"""
            )
            print("created table Stafeta.DocChunk")

        cur.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'Stafeta' AND TABLE_NAME = 'DocChunk'"
        )
        existing = {str(row[0]).upper() for row in cur.fetchall()}
        for name, ddl in DOC_CHUNK_EXTRA_COLUMNS:
            if name.upper() not in existing:
                cur.execute(f"ALTER TABLE Stafeta.DocChunk ADD COLUMN {name} {ddl}")
                print(f"added column DocChunk.{name}")

        cur.execute(
            "SELECT INDEX_NAME FROM INFORMATION_SCHEMA.INDEXES WHERE TABLE_SCHEMA = 'Stafeta' AND TABLE_NAME = 'DocChunk'"
        )
        indexes = {str(row[0]).upper() for row in cur.fetchall()}  # DISTINCT would return SQLUPPER-collated names
        for name, spec in DOC_CHUNK_INDEXES:
            if name.upper() in indexes:
                continue
            try:
                cur.execute(f"CREATE INDEX {name} ON TABLE Stafeta.DocChunk {spec}")
                print(f"created index {name}")
            except Exception as exc:  # noqa: BLE001 - older IRIS versions lack HNSW/iFind; search degrades
                if name not in OPTIONAL_INDEXES:
                    raise
                print(f"index {name} not created ({exc}); search falls back (exact / vector-only)")
    finally:
        cur.close()
        conn.close()


def check_fhir() -> None:
    url = f"http://{HOST}:{WEB_PORT}{ENDPOINT}/metadata"
    token = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    req = urllib.request.Request(url, headers={"Accept": "application/fhir+json", "Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(f"FHIR metadata: HTTP {resp.status} at {url}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"FHIR metadata failed: HTTP {exc.code} at {url}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"FHIR metadata unreachable at {url}: {exc.reason}") from exc


if __name__ == "__main__":
    wait_ready()
    ensure_namespace_and_fhir()
    ensure_vector_table()
    check_fhir()
    print("bootstrap done — next: make seed")
