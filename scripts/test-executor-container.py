#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Exercise the built image offline, using disposable state and no real broker."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["docker", *args], text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError(f"Docker test failed ({result.returncode}):\n"
                           f"{result.stdout}\n{result.stderr}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="follow-executor:0.3.1")
    args = parser.parse_args()
    names = []
    with tempfile.TemporaryDirectory(prefix="follow-container-test-") as directory:
        root = Path(directory)
        for name in ("config", "state"):
            (root / name).mkdir(mode=0o700)
        options = [
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--init", "--pids-limit", "128",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--mount", f"type=bind,src={root / 'config'},dst=/config",
            "--mount", f"type=bind,src={root / 'state'},dst=/state",
            "--mount", f"type=bind,src={ROOT / 'tests'},dst=/tests,readonly",
        ]

        def fixture(action: str):
            return docker("run", "--rm", *options, "--entrypoint", "python", args.image,
                          "/tests/container/lifecycle.py", action)

        def start() -> str:
            name = f"follow-container-test-{uuid.uuid4().hex[:12]}"
            names.append(name)
            docker("run", "-d", "--name", name, *options, "--env", f"TEST_RUN={name}",
                   "--entrypoint", "python", args.image, "/tests/container/lifecycle.py", "run")
            return name

        def wait_for(name, predicate):
            deadline = time.monotonic() + 25
            last = None
            while time.monotonic() < deadline:
                try:
                    last = json.loads((root / "state/snapshot.json").read_text())
                    if last["run"] == name and predicate(last):
                        return last
                except FileNotFoundError:
                    pass
                time.sleep(0.1)
            logs = docker("logs", name, check=False).stderr
            raise AssertionError(f"Timed out: {last}; fixture logs: {logs}")

        def stopped(name, expected):
            result = docker("wait", name).stdout.strip()
            assert result == str(expected), (name, result)
            with sqlite3.connect(root / "state/executor.sqlite3") as db:
                assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

        try:
            # The default command is help: image launch alone must never start trading.
            result = docker("run", "--rm", "--network", "none", args.image)
            assert "usage:" in result.stdout
            package_check = """
import os
from pathlib import Path
import follow_executor
from ibapi.client import EClient
from ibapi.order_cancel import OrderCancel
assert os.getuid() != 0
assert str(follow_executor.__file__).endswith('.pyc')
assert not list(Path(follow_executor.__file__).parent.rglob('*.py'))
try:
    Path('/etc/container-write-test').write_text('forbidden')
except OSError:
    pass
else:
    raise AssertionError('root filesystem was writable')
"""
            docker("run", "--rm", "--network", "none", "--read-only", "--entrypoint",
                   "python", args.image, "-c", package_check)
            # Run behavioral regressions against installed .pyc modules, with only
            # test fixtures mounted. No editable application or dev dependencies.
            regression = docker(
                "run", "--rm", *options, "--workdir", "/tests", "--entrypoint", "python",
                args.image, "-m", "unittest", "test_executor_engine", "test_executor_ibkr",
                "test_executor_service", "test_executor_protection",
                "test_executor_setup", "test_executor_notifications",
                "test_position_notifications", "test_service_notifications",
                "test_maintenance", "test_readiness", "test_balance_sizing",
                "test_gateway", "test_gateway_docker", "test_gateway_login", "test_gateway_health",
                "test_stack",
            )
            print("\n".join(regression.stderr.strip().splitlines()[-4:]), flush=True)
            fixture("init")
            first = start()
            wait_for(first, lambda s: s["entries"] == s["stops"] == s["working_stops"] == 1
                     and s["expected_position"] == s["position"] == 2 and s["halt"] is None)

            # A second real CLI process must fail before contacting any endpoint.
            duplicate = docker("run", "--rm", *options, args.image, "check", "--skip-broker",
                               "--config", "/config/executor.json", check=False)
            assert duplicate.returncode == 2 and "running" in duplicate.stderr
            # A different config filename must still contend on the shared journal.
            alternate = root / "config/alternate.json"
            alternate.write_bytes((root / "config/executor.json").read_bytes())
            duplicate = docker("run", "--rm", *options, args.image, "check", "--skip-broker",
                               "--config", "/config/alternate.json", check=False)
            assert duplicate.returncode == 2 and "running" in duplicate.stderr
            with (root / "config/executor.json.lock").open("r+") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    raise AssertionError("Native process could bypass the container lock")

            (root / "state/outage").touch()
            wait_for(first, lambda s: not s["connected"])
            (root / "state/outage").unlink()
            wait_for(first, lambda s: s["connected"] and s["entries"] == s["stops"] == 1)
            docker("stop", "--time", "20", first)
            stopped(first, 0)
            assert (root / "state/clean-stop").read_text() == first

            second = start()
            wait_for(second, lambda s: s["entries"] == s["stops"] == s["working_stops"] == 1
                     and s["expected_position"] == s["position"] == 2 and s["halt"] is None)
            docker("kill", "--signal", "KILL", second)
            stopped(second, 137)

            third = start()
            wait_for(third, lambda s: s["entries"] == s["stops"] == s["working_stops"] == 1
                     and s["halt"] is None)
            (root / "state/flatten").touch()
            wait_for(third, lambda s: s["seq"] == 2 and s["position"] == s["expected_position"] == 0
                     and s["working_stops"] == 0 and s["entries"] == 1)
            docker("stop", "--time", "20", third)
            stopped(third, 0)
            (root / "state/flatten").unlink()
            fixture("halt")

            fourth = start()
            wait_for(fourth, lambda s: s["seq"] == 2 and s["position"] == 0
                     and s["entries"] == 1 and s["halt"] == "container recovery test")
            docker("stop", "--time", "20", fourth)
            stopped(fourth, 0)
            print("PASS: bytecode image, non-root/read-only runtime, shared locks, simulated reconnect,")
            print("SIGTERM, SIGKILL/replacement, persistent journal/stops, replay protection and halt retention.")
            print("All fixtures used --network none; no Gateway, relay or real account was contacted.")
        finally:
            for name in names:
                docker("rm", "--force", name, check=False)


if __name__ == "__main__":
    main()
