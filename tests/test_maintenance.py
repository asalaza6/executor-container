# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import signal
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from follow_executor import gateway, gateway_docker, maintenance, stack
from follow_executor.config import ConfigError
from follow_executor.journal import Journal
from follow_executor.local import private_write
from follow_executor.maintenance_probe import FlatAccountProbe, check
from follow_executor.maintenance_state import journal_snapshot
from follow_executor.setup import initial_config


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, HOME=str(self.root / "home"),
                         XDG_CONFIG_HOME=str(self.root / "config"), XDG_STATE_HOME=str(self.root / "state"))
        env.start()
        self.addCleanup(env.stop)
        self.old = self.release("old", "a")
        self.new = self.release("new", "b")
        with patch("builtins.input", side_effect=["paper", "DU1234567", "MNQ", "1"]), \
                patch("getpass.getpass", return_value="private-test-token"), contextlib.redirect_stdout(io.StringIO()):
            initial_config(self.old.config)
        self.config = self.old.current_config()
        journal = Journal(self.config.journal_path)
        journal.record_signal(1, "test history")
        journal.mark_trade("finished", "closed", "test")
        journal.halt("preserve this halt")
        journal.close()
        settings = {"backend": "docker", "image": gateway_docker.IMAGE, "mode": "paper", "port": 4002,
                    "timezone": "America/New_York", "daily_restart": "23:45", "sunday_restart": "12:00", "vnc": False}
        private_write(self.old.gateway_dir / "gateway.json", json.dumps(settings))
        private_write(self.old.gateway_dir / "ibc.ini", gateway.ibc_config("fixture", "private-password", settings))
        private_write(self.old.gateway_unit, gateway.unit_text(self.old.config, self.old.release, settings["timezone"],
                                                              "docker", launcher=self.old.launcher))
        private_write(self.old.unit_path, "old executor service")
        private_write(self.old.pin, self.old.image_metadata()["id"] + "\n")

    def release(self, name, letter):
        path = self.root / name
        path.mkdir()
        wheel = path / "app.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            for module in ("journal", "config", "local", "gateway", "gateway_docker"):
                archive.writestr(f"follow_executor/{module}.pyc", "same compatible test bytes")
        image = {"id": "sha256:" + letter * 64, "platform": "linux/arm64", "archive": "image.tar.gz",
                 "archive_sha256": hashlib.sha256(b"image").hexdigest(),
                 "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
        meta = {"wheel": "app.whl", "wheel_sha256": image["wheel_sha256"],
                "bytecode_magic": importlib.util.MAGIC_NUMBER.hex(), "executor_image": image}
        for filename, contents in {"RELEASE.json": json.dumps(meta), "follow-stack": "fixture", "follow-container": "fixture",
                                   "scripts/stack-bootstrap.py": "fixture", "image.tar.gz": "image"}.items():
            private_write(path / filename, contents)
        (path / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(path)}\n"
            for p in sorted(path.rglob("*")) if p.is_file()))
        return stack.Stack(path)

    def install(self, target, image_id):
        private_write(target.pin, image_id + "\n")
        private_write(target.unit_path, "new service for " + image_id)

    @contextlib.contextmanager
    def environment(self, answers):
        def probe(wizard, image_id):
            return journal_snapshot(self.config) | {"account_flat": True, "orders_submitted": 0}

        with (patch.object(stack, "host_check"), patch.object(stack, "docker_access"),
              patch.object(stack, "service_state", return_value="inactive"),
              patch.object(stack, "command", return_value=Mock(stdout="")) as commands,
              patch.object(stack.Stack, "require_idle"), patch.object(stack.Stack, "prepare_image"),
              patch.object(stack.Stack, "install_image", autospec=True, side_effect=self.install),
              patch.object(stack.Stack, "maintenance_report", autospec=True, side_effect=probe),
              patch.object(gateway, "require_stopped"), patch.object(gateway_docker, "require_stopped"),
              patch("builtins.input", side_effect=answers), contextlib.redirect_stdout(io.StringIO())):
            yield commands

    def test_upgrade_and_rollback_retain_new_history_credentials_and_halt(self):
        original = journal_snapshot(self.config)
        credentials = (self.old.gateway_dir / "ibc.ini").read_bytes()
        with self.environment(["UPGRADE PAPER 1 MNQ"]) as commands:
            self.assertEqual(maintenance.switch(self.new, self.old.release), 0)
        self.assertEqual(self.old.pin.read_text().strip(), self.new.image_metadata()["id"])
        self.assertEqual(journal_snapshot(self.config), original)
        self.assertIn(str(self.new.launcher), self.new.gateway_unit.read_text())
        self.assertIn(f'Environment="XDG_STATE_HOME={self.new.state_base}"', self.new.gateway_unit.read_text())
        self.assertFalse(any("enable" in call.args[0] or "start" in call.args[0] for call in commands.call_args_list))
        saved = maintenance.read_record(self.new)
        backup = Path(saved["backup"]) / "journal.sqlite3"
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(backup) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        # Trades recorded after the upgrade must survive rollback; never restore the old backup.
        journal = Journal(self.config.journal_path)
        journal.record_signal(2, "new history after upgrade")
        journal.mark_trade("new-finished", "closed", "test")
        journal.close()
        after_trading = journal_snapshot(self.config)
        with self.environment(["ROLLBACK PAPER 1 MNQ"]):
            self.assertEqual(maintenance.switch(self.new, rollback=True), 0)
        self.assertEqual(journal_snapshot(self.config), after_trading)
        self.assertTrue(after_trading["halt_present"])
        self.assertEqual(self.old.pin.read_text().strip(), self.old.image_metadata()["id"])
        self.assertEqual(credentials, (self.old.gateway_dir / "ibc.ini").read_bytes())

    def test_interrupted_switch_blocks_start_until_explicit_restore(self):
        original_unit = self.old.unit_path.read_bytes()
        original = journal_snapshot(self.config)
        with self.environment(["UPGRADE PAPER 1 MNQ"]), \
                patch.object(stack.Stack, "install_image", side_effect=RuntimeError("fixture failure")), \
                self.assertRaisesRegex(RuntimeError, "fixture failure"):
            maintenance.switch(self.new, self.old.release)
        self.assertEqual(maintenance.read_record(self.new)["phase"], "pending")
        with self.assertRaisesRegex(ConfigError, "interrupted"):
            maintenance.require_complete(self.new)
        with self.environment(["ROLLBACK"]):
            self.assertEqual(maintenance.switch(self.new, rollback=True), 0)
        self.assertEqual(self.old.unit_path.read_bytes(), original_unit)
        self.assertEqual(journal_snapshot(self.config), original)
        self.assertEqual(maintenance.read_record(self.new)["phase"], "restored")

    def test_failed_account_probe_and_cancel_do_not_change_services(self):
        for answers, fail in ((["no"], False), (["UPGRADE PAPER 1 MNQ"], True)):
            with self.subTest(fail=fail), self.environment(answers) as commands:
                if fail:
                    with patch.object(stack.Stack, "maintenance_report", return_value={"account_flat": False}), \
                            self.assertRaisesRegex(ConfigError, "flat-account"):
                        maintenance.switch(self.new, self.old.release)
                else:
                    self.assertEqual(maintenance.switch(self.new, self.old.release), 3)
                self.assertFalse(any("disable" in call.args[0] for call in commands.call_args_list))
                self.assertIsNone(maintenance.read_record(self.new))

    def test_changed_configuration_between_probe_and_switch_is_refused(self):
        def altered(*args):
            self.config.token_path.write_text("changed fixture token")
            return journal_snapshot(self.config) | {"account_flat": True, "orders_submitted": 0}
        with self.environment(["UPGRADE PAPER 1 MNQ"]) as commands, \
                patch.object(stack.Stack, "maintenance_report", side_effect=altered), \
                self.assertRaisesRegex(ConfigError, "changed during maintenance"):
            maintenance.switch(self.new, self.old.release)
        self.assertFalse(any("disable" in call.args[0] for call in commands.call_args_list))

    def test_tampered_release_is_rejected_before_service_mutations(self):
        (self.new.release / "follow-container").write_text("damaged")
        with self.environment([]) as commands, self.assertRaisesRegex(ConfigError, "verification failed"):
            maintenance.switch(self.new, self.old.release)
        commands.assert_not_called()

    def test_incompatible_journal_or_gateway_code_requires_reviewed_migration(self):
        from follow_executor.release import verify_release

        def incompatible(path):
            result = verify_release(path)
            if path == self.new.release:
                result["compatibility"]["journal"] = "different code"
            return result

        with self.environment([]) as commands, \
                patch.object(maintenance, "verify_release", side_effect=incompatible), \
                self.assertRaisesRegex(ConfigError, "reviewed migration"):
            maintenance.switch(self.new, self.old.release)
        commands.assert_not_called()

    @contextlib.contextmanager
    def older_release(self, *, journal="same compatible test bytes"):
        from follow_executor.release import verify_release

        def versions(path):
            result = verify_release(path)
            if path == self.old.release:
                result["compatibility"].update(config="reviewed config", local="reviewed local")
                result["compatibility"]["journal"] = hashlib.sha256(journal.encode()).hexdigest()
            return result

        same = hashlib.sha256(b"same compatible test bytes").hexdigest()
        reviewed = {"0.2.0": {"config": "reviewed config", "local": "reviewed local"}}
        with patch.object(maintenance, "verify_release", side_effect=versions), \
                patch.object(maintenance, "REVIEWED_MIGRATIONS", reviewed), \
                patch.object(maintenance, "SHARED_MODULES", ("journal", "gateway", "gateway_docker")):
            self.assertEqual(verify_release(self.new.release)["compatibility"]["journal"], same)
            yield

    def test_reviewed_older_release_upgrades_and_rolls_back_only_with_a_fixed_size(self):
        with self.older_release(), self.environment(["UPGRADE PAPER 1 MNQ"]):
            self.assertEqual(maintenance.switch(self.new, self.old.release), 0)
        self.assertEqual(self.old.pin.read_text().strip(), self.new.image_metadata()["id"])
        fixed = self.old.config.read_text()
        raw = json.loads(fixed)
        raw.pop("instrument")
        raw["sizing"] = {"mode": "balance", "leverage_fraction": 0.5}
        private_write(self.old.config, json.dumps(raw))
        with self.older_release(), self.environment([]) as commands, \
                self.assertRaisesRegex(ConfigError, "cannot read balance sizing"):
            maintenance.switch(self.new, rollback=True)
        commands.assert_not_called()
        private_write(self.old.config, fixed)
        with self.older_release(), self.environment(["ROLLBACK PAPER 1 MNQ"]):
            self.assertEqual(maintenance.switch(self.new, rollback=True), 0)
        self.assertEqual(self.old.pin.read_text().strip(), self.old.image_metadata()["id"])

    def test_unreviewed_configuration_or_changed_journal_code_is_refused(self):
        with self.older_release(journal="older journal code"), self.environment([]) as commands, \
                self.assertRaisesRegex(ConfigError, "reviewed migration"):
            maintenance.switch(self.new, self.old.release)
        commands.assert_not_called()
        with self.older_release(), patch.object(maintenance, "REVIEWED_MIGRATIONS", {}), \
                self.environment([]), self.assertRaisesRegex(ConfigError, "reviewed migration"):
            maintenance.switch(self.new, self.old.release)

    def test_reviewed_gateway_pair_upgrade_and_rollback_preserve_state(self):
        from follow_executor.release import verify_release
        old_gateway, new_gateway = next(iter(maintenance.REVIEWED_GATEWAY_MIGRATIONS))
        def versions(path):
            result = verify_release(path)
            result["compatibility"]["gateway"] = old_gateway if path == self.old.release else new_gateway
            if path == self.old.release:
                result["compatibility"].update(maintenance.REVIEWED_MIGRATIONS["0.2.0"])
            return result
        before = journal_snapshot(self.config)
        credentials = (self.old.gateway_dir / "ibc.ini").read_bytes()
        with patch.object(maintenance, "verify_release", side_effect=versions):
            with self.environment(["UPGRADE PAPER 1 MNQ"]):
                self.assertEqual(maintenance.switch(self.new, self.old.release), 0)
            with self.environment(["ROLLBACK PAPER 1 MNQ"]):
                self.assertEqual(maintenance.switch(self.new, rollback=True), 0)
        self.assertEqual(journal_snapshot(self.config), before)
        self.assertEqual((self.old.gateway_dir / "ibc.ini").read_bytes(), credentials)

    def test_gateway_exception_rejects_unreviewed_endpoints_and_shared_changes(self):
        old_gateway, new_gateway = next(iter(maintenance.REVIEWED_GATEWAY_MIGRATIONS))
        old = dict(maintenance.REVIEWED_MIGRATIONS["0.2.0"],
                   gateway=old_gateway, journal="same", gateway_docker="same")
        new = dict(old, gateway=new_gateway, config="new config", local="new local")
        self.assertTrue(maintenance.reviewed_migration(old, new, rollback=False))
        self.assertTrue(maintenance.reviewed_migration(new, old, rollback=True))
        self.assertFalse(maintenance.reviewed_migration(new, old, rollback=False))
        for field in ("gateway", "journal", "gateway_docker", "config", "local"):
            with self.subTest(field=field):
                self.assertFalse(maintenance.reviewed_migration(dict(old, **{field: "unknown"}), new,
                                                                 rollback=False))
        for field in ("gateway", "journal", "gateway_docker"):
            with self.subTest(target=field):
                self.assertFalse(maintenance.reviewed_migration(old, dict(new, **{field: "unknown"}),
                                                                 rollback=False))

    def test_reviewed_list_names_the_published_release(self):
        self.assertEqual(set(maintenance.REVIEWED_MIGRATIONS), {"0.2.0"})
        for digests in maintenance.REVIEWED_MIGRATIONS.values():
            self.assertEqual(set(digests), {"config", "local"})
            self.assertTrue(all(len(value) == 64 for value in digests.values()))

    @unittest.skipUnless(hasattr(os, "fork"), "Linux crash recovery test")
    def test_process_kill_after_durable_marker_can_restore_without_journal_rewind(self):
        original = journal_snapshot(self.config)
        child = os.fork()
        if child == 0:
            try:
                def kill_after_partial_install(image_id):
                    self.install(self.new, image_id)
                    os.kill(os.getpid(), signal.SIGKILL)

                with self.environment(["UPGRADE PAPER 1 MNQ"]), \
                        patch.object(stack.Stack, "install_image", side_effect=kill_after_partial_install):
                    maintenance.switch(self.new, self.old.release)
            finally:
                os._exit(99)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), -signal.SIGKILL)
        self.assertEqual(maintenance.read_record(self.new)["phase"], "pending")
        with self.environment(["ROLLBACK"]):
            self.assertEqual(maintenance.switch(self.new, rollback=True), 0)
        self.assertEqual(journal_snapshot(self.config), original)
        self.assertEqual(self.old.pin.read_text().strip(), self.old.image_metadata()["id"])

    def test_pending_restore_refuses_changed_history(self):
        with self.environment(["UPGRADE PAPER 1 MNQ"]), \
                patch.object(stack.Stack, "install_image", side_effect=RuntimeError("interrupted")), \
                self.assertRaises(RuntimeError):
            maintenance.switch(self.new, self.old.release)
        journal = Journal(self.config.journal_path)
        journal.record_signal(2, "changed during interruption")
        journal.close()
        changed = journal_snapshot(self.config)
        with self.environment([]), self.assertRaisesRegex(ConfigError, "changed during maintenance"):
            maintenance.switch(self.new, rollback=True)
        self.assertEqual(journal_snapshot(self.config), changed)

    def test_probe_includes_other_symbols_and_blocks_all_order_submission(self):
        probe = FlatAccountProbe(self.config.ibkr, self.config.root)
        probe.on_position(self.config.ibkr.account, SimpleNamespace(conId=99), 0.5, 1)
        probe.on_open_order(5, SimpleNamespace(symbol="OTHER"), SimpleNamespace(account="", whatIf=False),
                            SimpleNamespace(status="Submitted"))
        self.assertEqual(probe.account_positions, {99: 0.5})
        self.assertEqual(probe.account_orders, {5: True})
        for method in (probe.place, probe.cancel, probe.what_if):
            with self.assertRaises(ConfigError):
                method(None)
        with patch("follow_executor.maintenance_probe.FlatAccountProbe", return_value=probe), \
                patch.object(probe, "connect"), patch.object(probe, "disconnect"), \
                patch.object(probe, "refresh"), patch.object(probe, "wait_for_snapshot"):
            probe._managed = (self.config.ibkr.account,)
            with self.assertRaisesRegex(ConfigError, "positions or working orders"):
                check(self.config)
