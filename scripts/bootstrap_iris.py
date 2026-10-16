"""Idempotent bootstrap of an InterSystems IRIS for Health container for Štafeta.

Works against a local docker container or the team's Azure Container Instance (no shell needed):
  1. waits until the superserver (1972) and web server (52773) answer,
  2. creates the FHIRSERVER namespace (HS.Util.Installer.Foundation) if missing,
  3. installs a FHIR R4 endpoint (JsonAdvSQL strategy) if missing,
  4. creates the vector-search table for document chunks (+ HNSW index when supported),
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


def ensure_vector_table() -> None:
    conn = iris.connect(HOST, PORT, NAMESPACE, USER, PASSWORD)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'Stafeta' AND TABLE_NAME = 'DocChunk'"
        )
        if cur.fetchone()[0]:
            print("table Stafeta.DocChunk exists")
            return
        cur.execute(
            f"""CREATE TABLE Stafeta.DocChunk (
                    DocRef VARCHAR(200) NOT NULL,
                    PatientRef VARCHAR(200),
                    Seq INTEGER NOT NULL,
                    AuthoredOn DATE,
                    ReceivedOn TIMESTAMP,
                    Text VARCHAR(32000),
                    Embedding VECTOR(DOUBLE, {EMBEDDING_DIM})
                )"""
        )
        print("created table Stafeta.DocChunk")
        try:
            cur.execute("CREATE INDEX DocChunkHNSW ON TABLE Stafeta.DocChunk (Embedding) AS HNSW(Distance='Cosine')")
            print("created HNSW index")
        except Exception as exc:  # noqa: BLE001 - older IRIS versions lack HNSW; exact search still works
            print(f"HNSW index not created ({exc}); falling back to exact VECTOR_COSINE search")
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
