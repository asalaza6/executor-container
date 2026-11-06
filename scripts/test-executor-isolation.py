#!/usr/bin/env python3.12
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Exercise production launcher and service mounts offline with synthetic credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="follow-executor:0.3.1")
    parser.add_argument("--launcher", type=Path, default=ROOT / "follow-container")
    args = parser.parse_args()
    real_docker = shutil.which("docker")
    image = subprocess.check_output([real_docker, "image", "inspect", "--format", "{{.Id}}", args.image],
                                    text=True).strip()
    with tempfile.TemporaryDirectory(prefix="executor-isolation-") as directory:
        root = Path(directory)
        config, state = root / "config space/follow-executor", root / "state space/follow-executor"
        gateway, backups = config / "gateway", state / "maintenance/old/config/gateway"
        for path in (gateway, backups, root / "bin"):
            path.mkdir(parents=True, mode=0o700)
        # No production configuration or credentials are read by this test.
        secrets = (gateway / "ibc.ini", gateway / "vnc.password", backups / "ibc.ini")
        for path in secrets:
            path.write_text("synthetic-credential-canary-" + path.name)
            path.chmod(0o600)
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in secrets}
        (config / "gateway-alias").symlink_to(gateway / "ibc.ini")
        (state / "backup-alias").symlink_to(backups / "ibc.ini")
        env = dict(os.environ, PATH=f"{root / 'bin'}:{os.environ['PATH']}",
                   XDG_CONFIG_HOME=str(config.parent), XDG_STATE_HOME=str(state.parent),
                   TEST_CALLS=str(root / "calls.jsonl"), TEST_IMAGE=image,
                   FOLLOW_EXECUTOR_PROBE_IMAGE=image)
        # Capture real launch arguments without installing/starting a host service.
        # Replay Docker below with only networking and the test entrypoint changed.
        stub = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with open(os.environ['TEST_CALLS'], 'a') as out:
    out.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')
if Path(sys.argv[0]).name == 'docker' and sys.argv[1:3] == ['image', 'inspect']:
    print(os.environ['TEST_IMAGE'])
elif Path(sys.argv[0]).name == 'systemctl' and any(a in sys.argv for a in ['is-active', 'is-enabled']):
    raise SystemExit(1)
'''
        for name in ("docker", "systemctl"):
            path = root / "bin" / name
            path.write_text(stub)
            path.chmod(0o755)

        def launcher(action):
            result = subprocess.run([str(args.launcher.resolve()), action], env=env,
                                    text=True, capture_output=True, check=False)
            assert result.returncode == 0, result.stderr
            return [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]

        def probe(arguments, action):
            assert arguments[0] == "run"
            options = arguments[1:arguments.index(image)]
            assert options[options.index("--network") + 1] == "host"
            options[options.index("--network") + 1] = "none"
            command = [real_docker, "run", *options, "--mount",
                       f"type=bind,source={ROOT / 'tests'},target=/tests,readonly",
                       "--entrypoint", "python", image, "/tests/container/credential_isolation.py", action]
            result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=60)
            assert result.returncode == 0, result.stderr
            assert result.stdout.startswith("PASS:"), result.stdout
            assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in secrets}

        launcher("install")
        for action in ("configure", "settings", "discord", "check", "maintenance-check", "status"):
            calls = launcher(action)
            assert calls[-1][:2] == ["docker", "run"]
            probe(calls[-1][1:], action)
        unit = next((config.parent / "systemd/user").glob("*.service"))
        line = next(line for line in unit.read_text().splitlines() if line.startswith("ExecStart="))
        arguments = shlex.split(line.removeprefix("ExecStart="))[1:]
        probe(arguments, "service")
        probe(arguments, "service-replacement")
        print("PASS: real Docker denies Gateway credentials, VNC password, maintenance backup and symlink aliases")
        print("PASS: production CLI/service mounts; setup/settings/Discord atomic writes; journal and host secrets retained")
        print("All probes used synthetic credentials and --network none; no host services or accounts were contacted.")


if __name__ == "__main__":
    main()
