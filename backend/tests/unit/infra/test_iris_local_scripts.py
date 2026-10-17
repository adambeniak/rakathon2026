"""`make up-local` / `make test-iris-local` start a FRESH local IRIS: the password file must be prepared (issue #43).

The scripts run for real in a temporary secrets directory (IRIS_SECRETS_DIR) with a fake `docker` first on the PATH,
so nothing touches the project's own secrets directory or starts a container.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from app.settings import REPO_ROOT

PREPARE = REPO_ROOT / "scripts" / "iris_local_prepare.sh"
UP_LOCAL = REPO_ROOT / "scripts" / "up_local.sh"
PASSWORD = "local-Pa55word_ok"
BASH = shutil.which("bash") or "/bin/bash"

FAKE_DOCKER = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_DOCKER_LOG"
case " $* " in
  *" ps "*) printf '%b' "${FAKE_DOCKER_PS:-}" ;;
esac
"""


@pytest.fixture
def secrets(tmp_path: Path) -> Path:
    directory = tmp_path / "secrets"
    directory.mkdir()
    return directory


@pytest.fixture
def docker_log(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    return tmp_path / "docker.log"


def run(
    script: Path,
    secrets: Path,
    *args: str,
    docker_log: Path | None = None,
    running: bool = False,
    env_file: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "IRIS_SECRETS_DIR": str(secrets), "ENV_FILE": str(env_file or secrets.parent / "no.env")}
    if docker_log is not None:
        env["PATH"] = f"{docker_log.parent / 'bin'}{os.pathsep}{env['PATH']}"
        env["FAKE_DOCKER_LOG"] = str(docker_log)
        env["FAKE_DOCKER_PS"] = "iris\\n" if running else ""
    return subprocess.run(  # noqa: S603 - fixed scripts from this repository, bash from PATH
        [BASH, str(script), *args], env=env, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def test_a_leftover_sentinel_is_removed_so_a_fresh_container_sets_the_password(secrets: Path) -> None:
    (secrets / "password.txt").write_text(PASSWORD, encoding="utf-8")
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
    assert "IRIS_PASSWORD" in refused.stderr
    assert generated.returncode == 0
    password = (secrets / "password.txt").read_text(encoding="utf-8")
    assert len(password) >= 16
    assert "\n" not in password
    assert (secrets / "password").read_text(encoding="utf-8") == password


def test_up_local_prepares_the_password_for_a_fresh_container_and_starts_the_stack(
    secrets: Path, docker_log: Path
) -> None:
    (secrets / "password.txt").write_text(PASSWORD, encoding="utf-8")
    (secrets / "password.done").write_text("", encoding="utf-8")

    result = run(UP_LOCAL, secrets, docker_log=docker_log, running=False)

    assert result.returncode == 0, result.stderr
    assert not (secrets / "password.done").exists()
    assert (secrets / "password").read_text(encoding="utf-8") == PASSWORD
    calls = docker_log.read_text(encoding="utf-8").splitlines()
    assert calls[-1] == "compose -f docker-compose.yml -f docker-compose.local-iris.yml up -d --build"


def test_up_local_leaves_a_running_iris_alone(secrets: Path, docker_log: Path) -> None:
    (secrets / "password.txt").write_text(PASSWORD, encoding="utf-8")
    (secrets / "password.done").write_text("", encoding="utf-8")  # the running container's own sentinel

    result = run(UP_LOCAL, secrets, docker_log=docker_log, running=True)

    assert result.returncode == 0, result.stderr
    assert (secrets / "password.done").exists()  # not touched
    assert not (secrets / "password").exists()  # no plaintext copy is written for a container that has its password
    assert docker_log.read_text(encoding="utf-8").splitlines()[-1].endswith("up -d --build")


def test_up_local_without_a_password_fails_before_starting_anything(secrets: Path, docker_log: Path) -> None:
    result = run(UP_LOCAL, secrets, docker_log=docker_log, running=False)

    assert result.returncode == 1
    assert "IRIS_PASSWORD" in result.stderr
    assert not any("up -d" in line for line in docker_log.read_text(encoding="utf-8").splitlines())


@pytest.mark.parametrize(("env_line", "warns"), [(f"IRIS_PASSWORD={PASSWORD}", False), ('IRIS_PASSWORD="other"', True)])
def test_up_local_warns_when_the_backend_password_differs_without_printing_either(
    secrets: Path, docker_log: Path, tmp_path: Path, env_line: str, warns: bool
) -> None:
    (secrets / "password.txt").write_text(PASSWORD, encoding="utf-8")
    env_file = tmp_path / "test.env"
    env_file.write_text(f"FHIR_BASE_URL=http://x\n{env_line}\n", encoding="utf-8")

    result = run(UP_LOCAL, secrets, docker_log=docker_log, running=False, env_file=env_file)

    assert result.returncode == 0, result.stderr
    assert ("WARNING: IRIS_PASSWORD" in result.stderr) is warns
    assert PASSWORD not in result.stdout + result.stderr
    assert "other" not in result.stdout + result.stderr


def test_the_makefile_targets_use_the_shared_scripts() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    test_script = (REPO_ROOT / "scripts" / "test_iris_local.sh").read_text(encoding="utf-8")

    assert "./scripts/up_local.sh" in makefile
    assert "./scripts/iris_local_prepare.sh --generate" in test_script
    assert "password.done" not in makefile  # the sentinel handling lives in the one helper
