# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Actual guest Docker/systemd release switching with a simulated flat-account gate.

Only for the disposable guest created by this directory's rehearsal. Never logs
into IBKR, starts a Gateway, follows signals or submits any order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if socket.gethostname() != "follow-rehearsal":
        raise RuntimeError("Refusing to run outside the disposable rehearsal guest")
    metadata = json.loads((args.new / "RELEASE.json").read_text())
    sys.path.insert(0, str(args.new / metadata["wheel"]))
    from follow_executor import gateway, gateway_docker, maintenance, stack
    from follow_executor.broker import Execution
    from follow_executor.journal import Journal
    from follow_executor.local import private_write
    from follow_executor.maintenance_state import journal_snapshot
    from follow_executor.release import verify_release

    old, new = stack.Stack(args.old), stack.Stack(args.new)
    verify_release(args.old)
    verify_release(args.new)
    current = new.current_config()
    assert current.ibkr.account == "DU1234567" and current.ibkr.account_type == "paper"
    assert current.token() == "disposable-rehearsal-token"
    assert not (new.gateway_dir / "gateway.json").exists()
    new.require_idle()
    new.require_gateway_ownership()
    old.prepare_image(old.image_metadata(), changing=True)
    old.install_image(old.image_metadata()["id"])
    settings = {"backend": "docker", "image": gateway_docker.IMAGE, "mode": "paper", "port": 4002,
                "timezone": "America/New_York", "daily_restart": "23:45", "sunday_restart": "12:00", "vnc": False}
    private_write(old.gateway_dir / "gateway.json", json.dumps(settings))
    private_write(old.gateway_dir / "ibc.ini", gateway.ibc_config("fixture-only", "fixture-only", settings))
    private_write(old.gateway_unit, gateway.unit_text(old.config, old.release, settings["timezone"],
                                                     "docker", launcher=old.launcher))
    stack.command(["systemctl", "--user", "daemon-reload"])
    journal = Journal(current.journal_path)
    journal.record_signal(1, "fixture history before upgrade")
    journal.record_execution(Execution("fixture-entry", 11, 42, "BOT", 1, 20000.25, "", "fixture"))
    journal.record_execution(Execution("fixture-exit", 12, 42, "SLD", 1, 20001.50, "", "fixture"))
    journal.halt("fixture halt must survive maintenance")
    journal.close()
    before = journal_snapshot(current)
    config_hash = maintenance.configuration_hash(old.config.parent)
    # Use the same named volume that Gateway would use; only a network-disabled
    # fixture container writes a sentinel, never the Gateway executable.
    volume = gateway_docker.volume_name(old.config, settings)
    stack.command(["docker", "volume", "create", "--label", f"{gateway_docker.LABEL}={gateway_docker.identity(old.config)}", volume])
    runtime = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--user", "0:0", "--mount", f"type=volume,src={volume},dst=/fixture",
               "--entrypoint", "python", new.image_metadata()["id"], "-c"]
    stack.command(runtime + ["from pathlib import Path; Path('/fixture/persist').write_text('gateway-settings-fixture')"])

    def probe(*_):
        # Exercise the real compiled container journal reader against host-created
        # SQLite data. Only the broker result is simulated, not the fingerprint.
        code = ("import json,sys; from follow_executor.config import load_config; "
                "from follow_executor.maintenance_state import journal_snapshot; "
                "print(json.dumps(journal_snapshot(load_config(sys.argv[1]))))")
        command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}"]
        for directory in (current.journal_path.parent, new.config.parent):
            command += ["--mount", f"type=bind,src={directory},dst={directory},readonly"]
        command += ["--entrypoint", "python", new.image_metadata()["id"], "-c", code, str(new.config)]
        result = json.loads(stack.command(command).stdout)
        return result | {"maintenance_ready": True, "orders_submitted": 0}

    with patch.object(stack.Stack, "maintenance_report", side_effect=probe), \
            patch.object(stack.sys.stdin, "isatty", return_value=True), \
            patch("builtins.input", return_value="UPGRADE PAPER 1 MNQ"):
        assert stack.main(new.release, ["upgrade", "--from", str(old.release)]) == 0
    assert new.pin.read_text().strip() == new.image_metadata()["id"]
    assert journal_snapshot(current) == before
    journal = Journal(current.journal_path)
    journal.record_signal(2, "newer fixture history must survive rollback")
    journal.close()
    newer = journal_snapshot(current)
    with patch.object(stack.Stack, "maintenance_report", side_effect=probe), \
            patch.object(stack.sys.stdin, "isatty", return_value=True), \
            patch("builtins.input", return_value="ROLLBACK PAPER 1 MNQ"):
        assert stack.main(new.release, ["rollback"]) == 0
    assert old.pin.read_text().strip() == old.image_metadata()["id"]
    assert journal_snapshot(current) == newer and newer["halt_present"]
    assert maintenance.configuration_hash(old.config.parent) == config_hash
    data = stack.command(runtime + ["from pathlib import Path; print(Path('/fixture/persist').read_text())"]).stdout.strip()
    assert data == "gateway-settings-fixture"
    for unit in (old.unit, gateway.SERVICE):
        assert stack.service_state(unit) == "inactive"
        assert subprocess.run(["systemctl", "--user", "is-enabled", "--quiet", unit], check=False).returncode != 0
    report = {"actual_guest_docker_systemd_upgrade_and_rollback": "passed", "account_gate": "simulated flat",
              "private_config_retained": True, "gateway_volume_retained": True, "newer_journal_history_retained": True,
              "host_container_journal_fingerprint_agrees": True,
              "halt_retained": True, "services_stopped_disabled": True, "real_account_contacted": False,
              "journal_sha256": newer["journal_sha256"], "config_sha256": config_hash,
              "volume_fixture_sha256": hashlib.sha256(data.encode()).hexdigest(), "orders_submitted": 0}
    private_write(args.report, json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
