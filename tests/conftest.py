import os
import sys
from pathlib import Path

import pytest

_tests_dir = Path(__file__).parent
_root_dir = _tests_dir.parent
sys.path.insert(0, str(_root_dir.absolute()))

import atex  # noqa: E402


def pytest_addoption(parser):
    parser.addoption(
        "--tf", action="store_true", help="Run tests on Testing Farm remotely",
    )


def pytest_sessionstart(session):
    if session.config.getoption("--tf"):
        if not os.environ.get("TESTING_FARM_API_TOKEN"):
            pytest.exit("TESTING_FARM_API_TOKEN not in environment", returncode=3)
        pytest_args = (a for a in session.config.invocation_params.args if a != "--tf")
        pytest_args_str = f" {' '.join(pytest_args)}" if session.config.args else ""
        res = atex.testingfarm.Reserve(
            #compose="CentOS-Stream-9",
            timeout=60,
        )
        with res as machine:
            options = {
                "Hostname": machine.host,
                "Port": machine.port,
                "User": machine.user,
                "IdentityFile": machine.ssh_key,
                "RequestTTY": "yes",
            }
            with atex.ssh.SSHConn(options) as conn:
                conn.ssh("dnf -q -y install rsync python3-pytest", check=True)
                conn.rsync("-r", f"{_root_dir}/", "remote:/tmp/atex")
                # pytest is messing with sys.stdin, which breaks color output
                # for the remote pytest (stdin is not console) - work around it
                # by duplicating stdout to stdin when stdout is tty
                stdin = sys.stdout if sys.stdout.isatty() else None
                proc = conn.ssh(f"cd /tmp/atex && pytest{pytest_args_str}", stdin=stdin)
                pytest.exit("Remote testing finished", returncode=proc.returncode)
    else:
        uid = os.geteuid()
        if uid != 0:
            raise pytest.UsageError("Local testing supported only for UID 0")
