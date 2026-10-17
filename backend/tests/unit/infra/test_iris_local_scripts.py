"""`make up-local` is the demo fallback in ONE command, and `make test-iris-local` shares its helpers (issue #43).

The scripts run for real in a temporary secrets directory with fake `docker`, `uv` and `curl` first on the PATH
(one shared log), so nothing touches the project's own secrets directory or env file and no container is started.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from app.settings import REPO_ROOT

SCRIPTS = REPO_ROOT / "scripts"
PREPARE = SCRIPTS / "iris_local_prepare.sh"
UP_LOCAL = SCRIPTS / "up_local.sh"
TEST_LOCAL = SCRIPTS / "test_iris_local.sh"
PASSWORD = "local-Pa55word_ok"
BASH = shutil.which("bash") or "/bin/bash"
COMPOSE = "compose -f docker-compose.yml -f docker-compose.local-iris.yml"

FAKE_DOCKER = """#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
case " $* " in
  *" ps -q "*) echo fakecid ;;
  *" ps "*) printf '%b' "${FAKE_DOCKER_PS:-}" ;;
  *" inspect "*) echo "${FAKE_IRIS_HEALTH:-healthy}" ;;
  *" up "*)
    echo "env-at-up LOCAL_IRIS_PASSWORD=${LOCAL_IRIS_PASSWORD-unset} IRIS_HOST=${IRIS_HOST-unset}" \\
         "IRIS_PASSWORD=${IRIS_PASSWORD-unset}" >> "$FAKE_LOG"
    ;;
esac
"""
FAKE_UV = """#!/usr/bin/env bash
echo "uv $* :: cwd=$(basename "$PWD") IRIS_HOST=${IRIS_HOST-unset}" \\
     "IRIS_SUPERSERVER_PORT=${IRIS_SUPERSERVER_PORT-unset}" \\
     "IRIS_NAMESPACE=${IRIS_NAMESPACE-unset} IRIS_USER=${IRIS_USER-unset} IRIS_PASSWORD=${IRIS_PASSWORD-unset}" \\
     "FHIR_BASE_URL=${FHIR_BASE_URL-unset} STAFETA_ENV=${STAFETA_ENV-unset}" >> "$FAKE_LOG"
case "$*" in
  *bootstrap_iris*) [ -n "${FAKE_BOOTSTRAP_FAIL:-}" ] && { echo "credentials rejected" >&2; exit 1; } ;;
  *pytest*) printf '%s\\n' "${FAKE_PYTEST_OUT:-3 passed}"; exit "${FAKE_PYTEST_CODE:-0}" ;;
esac
exit 0
"""
FAKE_CURL = """#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
out=""
url=""
while [ $# -gt 0 ]; do
  [ "$1" = -o ] && out="$2"
  url="$1"
  shift
done
case "$url" in
  */api/cases) printf '%s' "$FAKE_CASES_BODY" > "$out"; printf '%s' "$FAKE_CASES_CODE" ;;
  *) printf '%s' "$FAKE_HEALTH_BODY" > "$out"; printf '%s' "$FAKE_HEALTH_CODE" ;;
esac
"""
_LEAKY = ("IRIS_", "LOCAL_IRIS", "FHIR_BASE_URL", "SCENARIO", "STAFETA_", "BACKEND_HEALTH", "FAKE_")


@pytest.fixture
def secrets(tmp_path: Path) -> Path:
    directory = tmp_path / "secrets"
    directory.mkdir()
    return directory


@pytest.fixture
def fakes(tmp_path: Path) -> Path:
    """Directory with the fake docker/uv/curl; the shared log is `<tmp>/calls.log`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", FAKE_DOCKER), ("uv", FAKE_UV), ("curl", FAKE_CURL)):
        path = bin_dir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return tmp_path


def run(
    script: Path,
    secrets: Path,
    *args: str,
    fakes: Path | None = None,
    running: bool = False,
    **extra: str,
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(_LEAKY)}  # nothing from the developer's shell
    env["IRIS_SECRETS_DIR"] = str(secrets)
    if fakes is not None:
        env["PATH"] = f"{fakes / 'bin'}{os.pathsep}{env['PATH']}"
        env["FAKE_LOG"] = str(fakes / "calls.log")
        env["FAKE_DOCKER_PS"] = "iris\\n" if running else ""
        env.update(
            IRIS_HEALTH_ATTEMPTS="2",
            IRIS_HEALTH_INTERVAL="0",
            BACKEND_HEALTH_ATTEMPTS="2",
            BACKEND_HEALTH_INTERVAL="0",
            FAKE_HEALTH_CODE="200",
            FAKE_HEALTH_BODY='{"status":"ok"}',
            FAKE_CASES_CODE="200",
            FAKE_CASES_BODY="[]",
        )
    env.update(extra)
    return subprocess.run(  # noqa: S603 - fixed scripts from this repository
        [BASH, str(script), *args], env=env, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def calls(fakes: Path) -> list[str]:
    log = fakes / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def first(lines: list[str], prefix: str) -> int:
    return next(i for i, line in enumerate(lines) if line.startswith(prefix))


def starts(lines: list[str], prefix: str) -> list[str]:
    return [line for line in lines if line.startswith(prefix)]


def code_lines(text: str) -> str:
    """The file without comment lines (a comment may well mention what the code must not do)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def ready(secrets: Path) -> None:
    (secrets / "password.txt").write_text(PASSWORD, encoding="utf-8")


# --- the password file of a FRESH container (the sentinel fix) ---


def test_a_leftover_sentinel_is_removed_so_a_fresh_container_sets_the_password(secrets: Path) -> None:
    ready(secrets)
    (secrets / "password.done").write_text("", encoding="utf-8")  # left behind by the previous container

    result = run(PREPARE, secrets)

    assert result.returncode == 0, result.stderr
    assert not (secrets / "password.done").exists()
    assert (secrets / "password").read_text(encoding="utf-8") == PASSWORD


def test_the_copy_handed_to_iris_has_no_trailing_newline_and_the_container_user_can_delete_it(secrets: Path) -> None:
    (secrets / "password.txt").write_text(PASSWORD + "\n", encoding="utf-8")  # made with `echo`

    run(PREPARE, secrets)

    assert (secrets / "password").read_bytes() == PASSWORD.encode()
    assert stat.S_IMODE((secrets / "password").stat().st_mode) == 0o666
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o777  # IRIS deletes the file after reading it


def test_a_missing_password_is_an_error_unless_the_test_run_may_generate_one(secrets: Path) -> None:
    refused = run(PREPARE, secrets)
    generated = run(PREPARE, secrets, "--generate")

    assert refused.returncode == 1
    assert "password.txt" in refused.stderr
    assert generated.returncode == 0
    password = (secrets / "password.txt").read_text(encoding="utf-8")
    assert len(password) >= 16
    assert "\n" not in password
    assert (secrets / "password").read_text(encoding="utf-8") == password


# --- make up-local: one command ---


def test_up_local_does_everything_in_order_and_ends_with_ok(secrets: Path, fakes: Path) -> None:
    ready(secrets)
    (secrets / "password.done").write_text("", encoding="utf-8")

    result = run(UP_LOCAL, secrets, fakes=fakes)

    assert result.returncode == 0, result.stderr
    assert (
        result.stdout.strip()
        .splitlines()[-1]
        .startswith("OK: backend healthy and GET /api/cases answers 200 at http://127.0.0.1:8000")
    )
    assert not (secrets / "password.done").exists()  # fresh container: the sentinel fix ran
    lines = calls(fakes)
    steps = [
        first(lines, f"docker {COMPOSE} up -d iris"),
        first(lines, "docker inspect"),  # waited for healthy
        first(lines, "uv run --with intersystems-irispython==5.4.1 python scripts/bootstrap_iris.py"),
        first(lines, "uv run python -m app.seed"),
        first(lines, f"docker {COMPOSE} up -d --build"),
        first(lines, "curl"),
    ]
    assert steps == sorted(steps)
    assert len(set(steps)) == len(steps)


def test_the_backend_gets_the_local_password_and_no_host_side_settings_leak_into_compose(
    secrets: Path, fakes: Path
) -> None:
    ready(secrets)

    result = run(UP_LOCAL, secrets, fakes=fakes)

    assert result.returncode == 0, result.stderr
    env_at_up = starts(calls(fakes), "env-at-up")
    assert env_at_up  # every compose `up` sees the local password ...
    assert all(f"LOCAL_IRIS_PASSWORD={PASSWORD} IRIS_HOST=unset IRIS_PASSWORD=unset" in line for line in env_at_up)
    assert PASSWORD not in result.stdout + result.stderr  # ... and it is never printed


def test_bootstrap_and_seed_use_explicit_local_connection_settings(secrets: Path, fakes: Path) -> None:
    ready(secrets)

    run(UP_LOCAL, secrets, fakes=fakes)

    bootstrap, seed = starts(calls(fakes), "uv run")
    for line in (bootstrap, seed):
        assert "IRIS_HOST=localhost IRIS_SUPERSERVER_PORT=1972" in line
        assert "IRIS_NAMESPACE=FHIRSERVER IRIS_USER=_SYSTEM" in line
        assert f"IRIS_PASSWORD={PASSWORD}" in line
        assert "FHIR_BASE_URL=http://localhost:52773/fhir/r4 STAFETA_ENV=local" in line
    assert "cwd=backend" in seed


def test_the_default_scenario_is_demo_start_without_the_embedding_model(secrets: Path, fakes: Path) -> None:
    ready(secrets)

    run(UP_LOCAL, secrets, fakes=fakes)

    [seed] = starts(calls(fakes), "uv run python -m app.seed")
    assert seed.startswith("uv run python -m app.seed --scenario demo-start --no-index ::")


def test_the_story_scenario_can_be_chosen_and_builds_the_vector_index(secrets: Path, fakes: Path) -> None:
    ready(secrets)

    result = run(UP_LOCAL, secrets, fakes=fakes, SCENARIO="story")

    [seed] = starts(calls(fakes), "uv run python -m app.seed")
    assert seed.startswith("uv run python -m app.seed --scenario story ::")
    assert "scenario story" in result.stdout


def test_an_unknown_scenario_is_refused_before_anything_starts(secrets: Path, fakes: Path) -> None:
    ready(secrets)

    result = run(UP_LOCAL, secrets, fakes=fakes, SCENARIO="everything")

    assert result.returncode == 2
    assert "SCENARIO must be demo-start or story" in result.stderr
    assert calls(fakes) == []


def test_a_running_iris_is_left_alone_but_still_bootstrapped_seeded_and_checked(secrets: Path, fakes: Path) -> None:
    ready(secrets)
    (secrets / "password.done").write_text("", encoding="utf-8")  # the running container's own sentinel

    result = run(UP_LOCAL, secrets, fakes=fakes, running=True)

    assert result.returncode == 0, result.stderr
    assert (secrets / "password.done").exists()  # not touched
    assert not (secrets / "password").exists()  # no plaintext copy for a container that already has its password
    assert starts(calls(fakes), "uv run")  # idempotent bootstrap and seed still run
    assert "OK:" in result.stdout


def test_without_a_local_password_nothing_is_started(secrets: Path, fakes: Path) -> None:
    result = run(UP_LOCAL, secrets, fakes=fakes)

    assert result.returncode == 1
    assert "password.txt" in result.stderr
    assert not any(" up " in line for line in calls(fakes))


def test_an_iris_that_never_becomes_healthy_fails_before_bootstrap_and_backend(secrets: Path, fakes: Path) -> None:
    ready(secrets)

    result = run(UP_LOCAL, secrets, fakes=fakes, FAKE_IRIS_HEALTH="starting")

    assert result.returncode == 1
    assert "FAIL: the local IRIS container is not healthy" in result.stderr
    lines = calls(fakes)
    assert not starts(lines, "uv")
    assert not any("up -d --build" in line for line in lines)


def test_a_failed_bootstrap_stops_the_flow_and_shows_why(secrets: Path, fakes: Path) -> None:
    ready(secrets)

    result = run(UP_LOCAL, secrets, fakes=fakes, FAKE_BOOTSTRAP_FAIL="1")

    assert result.returncode == 1
    assert "FAIL: bootstrap or seed of the local IRIS failed" in result.stderr
    lines = calls(fakes)
    assert not starts(lines, "uv run python -m app.seed")  # no seed after a failed bootstrap
    assert not any("up -d --build" in line for line in lines)  # and no backend


def test_an_unhealthy_backend_ends_with_fail_the_response_and_where_to_look(secrets: Path, fakes: Path) -> None:
    ready(secrets)
    body = '{"status":"degraded","checks":{"fhir":{"ok":false,"detail":"FhirAuthError (HTTP 401)"}}}'

    result = run(UP_LOCAL, secrets, fakes=fakes, FAKE_HEALTH_CODE="503", FAKE_HEALTH_BODY=body)

    assert result.returncode == 1
    assert "FhirAuthError (HTTP 401)" in result.stderr
    assert "FAIL: backend health check answered HTTP 503" in result.stderr
    assert "logs backend" in result.stderr
    assert "OK:" not in result.stdout
    assert PASSWORD not in result.stdout + result.stderr


def test_the_final_check_also_asks_the_api_as_the_demo_coordinator(secrets: Path, fakes: Path) -> None:
    ready(secrets)

    result = run(UP_LOCAL, secrets, fakes=fakes)

    assert result.returncode == 0, result.stderr
    lines = starts(calls(fakes), "curl")
    assert lines[0].endswith("http://127.0.0.1:8000/api/health")
    assert lines[1].endswith("-H X-Demo-Role: coordinator http://127.0.0.1:8000/api/cases")  # after the health check


def test_a_healthy_backend_whose_api_refuses_the_coordinator_is_a_fail(secrets: Path, fakes: Path) -> None:
    ready(secrets)

    result = run(UP_LOCAL, secrets, fakes=fakes, FAKE_CASES_CODE="401", FAKE_CASES_BODY='{"title":"Unauthorized"}')

    assert result.returncode == 1
    assert "FAIL: GET /api/cases as the demo coordinator answered HTTP 401" in result.stderr
    assert "Unauthorized" in result.stderr  # the response body is shown
    assert "OK:" not in result.stdout


def test_the_api_is_not_asked_while_the_backend_is_unhealthy(secrets: Path, fakes: Path) -> None:
    ready(secrets)

    run(UP_LOCAL, secrets, fakes=fakes, FAKE_HEALTH_CODE="503", FAKE_HEALTH_BODY="{}")

    assert not any(line.endswith("/api/cases") for line in starts(calls(fakes), "curl"))


# --- make test-iris-local shares the helpers ---


def test_test_iris_local_runs_pytest_after_the_shared_bootstrap_and_seed_and_passes_its_arguments(
    secrets: Path, fakes: Path
) -> None:
    result = run(TEST_LOCAL, secrets, "-k", "referral", fakes=fakes)  # no password yet: the test run generates one

    assert result.returncode == 0, result.stderr
    assert len((secrets / "password.txt").read_text(encoding="utf-8")) >= 16
    lines = calls(fakes)
    steps = [
        first(lines, "uv run --with intersystems-irispython==5.4.1 python scripts/bootstrap_iris.py"),
        first(lines, "uv run python -m app.seed --scenario story ::"),
        first(lines, "uv run pytest"),
    ]
    assert steps == sorted(steps)
    pytest_call = lines[steps[2]]
    assert "pytest -m iris tests/integration -q -rs -k referral ::" in pytest_call
    assert "cwd=backend IRIS_HOST=localhost" in pytest_call  # explicit local settings reach pytest
    assert not any("up -d --build" in line for line in lines)  # only the IRIS container, never the backend


def test_test_iris_local_passes_on_the_pytest_exit_status(secrets: Path, fakes: Path) -> None:
    result = run(TEST_LOCAL, secrets, fakes=fakes, FAKE_PYTEST_CODE="3", FAKE_PYTEST_OUT="1 failed, 2 passed")

    assert result.returncode == 3


def test_test_iris_local_treats_skipped_iris_tests_as_a_failure(secrets: Path, fakes: Path) -> None:
    result = run(TEST_LOCAL, secrets, fakes=fakes, FAKE_PYTEST_OUT="11 skipped")

    assert result.returncode == 1
    assert "some iris tests were skipped" in result.stderr


def test_test_iris_local_leaves_a_running_iris_alone(secrets: Path, fakes: Path) -> None:
    ready(secrets)
    (secrets / "password.done").write_text("", encoding="utf-8")

    result = run(TEST_LOCAL, secrets, fakes=fakes, running=True)

    assert result.returncode == 0, result.stderr
    assert (secrets / "password.done").exists()
    assert not any(" up " in line for line in calls(fakes))


# --- wiring ---


def test_the_override_pins_every_iris_setting_to_the_local_one_without_reading_the_env_file() -> None:
    override = code_lines((REPO_ROOT / "docker-compose.local-iris.yml").read_text(encoding="utf-8"))
    base = code_lines((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert "IRIS_PASSWORD: ${LOCAL_IRIS_PASSWORD:-}" in override
    assert 'STAFETA_DEMO_MODE: "1"' in override  # the fallback is the demo ...
    assert 'STAFETA_LLM_CACHE: "1"' in override  # ... and it runs offline (cached LLM answers)
    for setting in (
        "IRIS_HOST: iris",
        "IRIS_NAMESPACE: FHIRSERVER",
        "IRIS_USER: _SYSTEM",
        "FHIR_BASE_URL: http://iris",
    ):
        assert setting in override
    assert "env_file" not in override  # the override adds to the base file; it never points at another env file
    assert "env_file: .env" in base  # `make up` (team ACI) is unchanged


def test_the_make_targets_use_the_shared_scripts() -> None:
    makefile = code_lines((REPO_ROOT / "Makefile").read_text(encoding="utf-8"))
    test_script = code_lines((SCRIPTS / "test_iris_local.sh").read_text(encoding="utf-8"))

    assert "./scripts/up_local.sh" in makefile
    assert "source scripts/iris_local_lib.sh" in test_script
    assert "./scripts/iris_local_prepare.sh --generate" in test_script
    assert "password.done" not in makefile + test_script  # the sentinel handling lives in the one helper
