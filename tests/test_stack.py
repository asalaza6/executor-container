# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from follow_executor import gateway, gateway_docker, stack
from follow_executor.config import ConfigError
from follow_executor.local import exclusive, private_write
from follow_executor.setup import initial_config

IMAGE = "sha256:" + "b" * 64


class StackTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.release = self.root / "release"
        self.release.mkdir()
        self.env = patch.dict(os.environ, HOME=str(self.root / "home"),
                              XDG_CONFIG_HOME=str(self.root / "config"),
                              XDG_STATE_HOME=str(self.root / "state"))
        self.env.start()
        self.addCleanup(self.env.stop)
        self.wizard = stack.Stack(self.release)
        self.metadata = {"id": IMAGE, "platform": "linux/arm64", "wheel_sha256": "abc",
                         "archive": "images/executor.tar.gz", "archive_sha256": "abc"}
        (self.release / "RELEASE.json").write_text(json.dumps({
            "wheel_sha256": "abc", "executor_image": self.metadata,
        }))
        self.calls = []
        self.gateway_commands = []
        self.check_exit = 0

    def invoke(self, action, *options):
        self.calls.append((action, options))
        if action == "install":
            private_write(self.wizard.pin, IMAGE + "\n")
            private_write(self.wizard.unit_path, "test stopped unit")
        elif action == "configure":
            return initial_config(self.wizard.config)
        return self.check_exit if action == "check" else 0

    def gw_command(self, args, **kwargs):
        self.gateway_commands.append(args)
        return subprocess.CompletedProcess(args, 0, "inactive", "")

    @contextlib.contextmanager
    def setup_environment(self, answers):
        output = io.StringIO()
        with (patch.object(stack, "host_check"), patch.object(stack, "docker_access"),
              patch.object(stack, "docker_group_configured", return_value=True),
              patch.object(stack, "lingering", return_value=True),
              patch.object(stack.shutil, "which", return_value="/usr/bin/docker"),
              patch.object(self.wizard, "require_idle"),
              patch.object(stack, "service_state", return_value="inactive"),
              patch.object(stack, "command", return_value=Mock(stdout="")),
              patch.object(self.wizard, "prepare_image"),
              patch.object(self.wizard, "invoke", side_effect=self.invoke),
              patch.object(gateway, "run_command", side_effect=self.gw_command),
              patch.object(gateway_docker, "require_engine"),
              patch.object(gateway_docker, "require_stopped"),
              patch.object(gateway_docker, "prepare"),
              patch("builtins.input", side_effect=answers),
              patch("getpass.getpass", side_effect=["test-token", "vnc-pass", "vnc-pass", "test-user", "test-password"]),
              contextlib.redirect_stdout(output)):
            yield output

    def first_setup(self, last=""):
        return ["paper", "DU1234567", "MNQ", "1", "", "", "", last]

    def test_fresh_setup_configures_both_but_only_starts_gateway(self):
        with self.setup_environment(self.first_setup()) as output:
            self.assertEqual(self.wizard.setup(), 0)
        self.assertEqual([action for action, _ in self.calls], ["install", "configure", "check"])
        self.assertEqual(self.calls[-1], ("check", ("--quotes",)))
        self.assertEqual([call for call in self.gateway_commands if "enable" in call],
                         [["systemctl", "--user", "enable", "--now", gateway.SERVICE]])
        unit = self.wizard.gateway_unit.read_text()
        self.assertIn(f'ExecStart="{self.release}/follow-stack" gateway --config "{self.wizard.config}" run', unit)
        self.assertNotIn(".venv", unit)
        self.assertIn("container-stop", unit)
        self.assertIn(f'Environment="XDG_STATE_HOME={self.wizard.state_base}"', unit)
        for secret in ("test-token", "test-user", "test-password", "vnc-pass"):
            self.assertNotIn(secret, output.getvalue())
            self.assertNotIn(secret, unit)
        self.assertIn("./follow-stack start", output.getvalue())

    def test_pause_and_resume_preserve_credentials_journal_and_skip_private_prompts(self):
        with self.setup_environment(self.first_setup("later")):
            self.assertEqual(self.wizard.setup(), 3)
        config = self.wizard.current_config()
        paths = [self.wizard.config, config.token_path, config.journal_path,
                 self.wizard.gateway_dir / "ibc.ini", self.wizard.gateway_dir / "gateway.json"]
        before = {path: path.read_bytes() for path in paths}
        self.calls.clear()
        with self.setup_environment([""]), patch("getpass.getpass", side_effect=AssertionError("Asked for saved credentials")):
            self.assertEqual(self.wizard.setup(), 0)
        self.assertEqual([action for action, _ in self.calls], ["install", "check"])
        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_recovery_password_typo_retries_without_aborting_setup(self):
        # Each refused recovery password repeats the three Gateway schedule questions.
        answers = ["paper", "DU1234567", "MNQ", "1", *[""] * 9, ""]
        with (self.setup_environment(answers) as output,
              patch("getpass.getpass", side_effect=["test-token", "too-long-password",
                    "vnc-pass", "mismatch", "vnc-pass", "vnc-pass", "test-user", "test-password"])):
            self.assertEqual(self.wizard.setup(), 0)
        self.assertTrue(self.wizard.gateway_unit.exists())
        self.assertEqual((self.wizard.gateway_dir / "vnc.password").read_text(), "vnc-pass\n")
        self.assertEqual(output.getvalue().count("Nothing was saved"), 2)
        self.assertNotIn("start", [action for action, _ in self.calls])
        for secret in ("test-token", "too-long-password", "vnc-pass", "mismatch", "test-user", "test-password"):
            self.assertNotIn(secret, output.getvalue())

    def test_cancelled_gateway_setup_reports_missing_step_and_resumes_saved_account(self):
        with (self.setup_environment(["paper", "DU1234567", "MNQ", "1", *[""] * 6]),
              patch("getpass.getpass", side_effect=["test-token", "too-long-password", KeyboardInterrupt]),
              self.assertRaises(KeyboardInterrupt)):
            self.wizard.setup()
        config = self.wizard.current_config()
        paths = [self.wizard.config, config.token_path, config.journal_path]
        before = {path: path.read_bytes() for path in paths}
        self.assertFalse((self.wizard.gateway_dir / "gateway.json").exists())
        self.assertFalse(self.wizard.gateway_unit.exists())
        self.calls.clear()
        with self.setup_environment([]) as output:
            self.wizard.doctor()
            with self.assertRaisesRegex(ConfigError, r"Gateway configuration \(step 4/5\)"):
                self.wizard.start()
        self.assertIn("Executor configuration: saved", output.getvalue())
        self.assertIn("Gateway configuration: needs setup (step 4/5)", output.getvalue())
        self.assertIn("Gateway service definition: missing (step 4/5)", output.getvalue())
        self.assertEqual(self.calls, [])
        with (self.setup_environment(["", "", "", ""]),
              patch("getpass.getpass", side_effect=["vnc-pass", "vnc-pass", "test-user", "test-password"])):
            self.assertEqual(self.wizard.setup(), 0)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        self.assertEqual([action for action, _ in self.calls], ["install", "check"])

    def test_other_gateway_configure_refusals_are_not_retried(self):
        with (self.setup_environment(self.first_setup()),
              patch.object(gateway, "configure", side_effect=ConfigError("Gateway setup cancelled")) as configure,
              self.assertRaisesRegex(ConfigError, "Gateway setup cancelled")):
            self.wizard.setup()
        configure.assert_called_once()

    def test_missing_gateway_files_are_not_reported_as_permissions_error(self):
        directory = self.wizard.gateway_dir
        with self.setup_environment([]):
            with self.assertRaisesRegex(ConfigError, "gateway.json is missing"):
                self.wizard.gateway_action("status")
            directory.mkdir(parents=True, exist_ok=True)
            private_write(directory / "gateway.json", json.dumps({"backend": "docker"}))
            with self.assertRaisesRegex(ConfigError, "ibc.ini is missing"):
                self.wizard.gateway_action("status")
            (directory / "ibc.ini").symlink_to(directory / "absent")
            with self.assertRaisesRegex(ConfigError, "private regular file"):
                self.wizard.gateway_action("status")

    def test_failed_readiness_does_not_start_or_reset_and_can_retry(self):
        self.check_exit = 1
        with self.setup_environment(self.first_setup()) as output:
            self.assertEqual(self.wizard.setup(), 1)
        self.assertIn("did not pass", output.getvalue())
        self.assertNotIn("start", [action for action, _ in self.calls])
        self.check_exit = 0
        with self.setup_environment([""]):
            self.assertEqual(self.wizard.setup(), 0)
        self.assertNotIn("resume", [action for action, _ in self.calls])

    def test_existing_other_gateway_is_refused_before_mutations(self):
        private_write(self.wizard.gateway_unit, 'ExecStart="/other/.venv/bin/follow-executor" gateway run\n')
        with self.setup_environment([]), self.assertRaisesRegex(ConfigError, "another installation"):
            self.wizard.setup()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gateway_commands, [])

    def test_saved_account_and_gateway_must_match_before_login(self):
        with self.setup_environment(self.first_setup("later")):
            self.wizard.setup()
        raw = json.loads(self.wizard.config.read_text())
        raw["ibkr"]["port"] = 4500
        private_write(self.wizard.config, json.dumps(raw))
        self.gateway_commands.clear()
        with self.setup_environment([]), self.assertRaisesRegex(ConfigError, "mode/port differs"):
            self.wizard.setup()
        self.assertFalse(any("enable" in command for command in self.gateway_commands))

    def test_explicit_gateway_reconfigure_can_repair_interrupted_save(self):
        with self.setup_environment(self.first_setup("later")):
            self.wizard.setup()
        ini = self.wizard.gateway_dir / "ibc.ini"
        ini.write_text(ini.read_text().replace("TradingMode=paper", "TradingMode=live"))
        with self.assertRaisesRegex(ConfigError, "inconsistent"):
            gateway.load_settings(self.wizard.gateway_dir)
        self.gateway_commands.clear()
        with self.setup_environment(["", "", ""]):
            self.assertEqual(self.wizard.gateway_action("configure", vnc=False), 0)
        self.assertEqual(gateway.load_settings(self.wizard.gateway_dir)["mode"], "paper")
        self.assertFalse(any("enable" in command for command in self.gateway_commands))

    def test_start_requires_exact_mode_and_size_confirmation(self):
        with self.setup_environment(self.first_setup("later")):
            self.wizard.setup()
        self.calls.clear()
        with self.setup_environment(["START LIVE 1 MNQ"]):
            self.assertEqual(self.wizard.start(), 3)
        self.assertEqual(self.calls, [])
        with self.setup_environment(["START PAPER 1 MNQ"]):
            self.assertEqual(self.wizard.start(), 0)
        self.assertEqual(self.calls, [("start", ())])

    def test_balance_start_confirmation_names_the_fraction(self):
        with self.setup_environment(["paper", "DU1234567", "balance", "0.5", "", "", "", "", "later"]):
            self.wizard.setup()
        self.calls.clear()
        with self.setup_environment(["START PAPER 1 MNQ"]):
            self.assertEqual(self.wizard.start(), 3)
        with self.setup_environment(["START PAPER BALANCE 0.5"]):
            self.assertEqual(self.wizard.start(), 0)
        self.assertEqual(self.calls, [("start", ())])

    def test_changed_image_is_not_silently_upgraded(self):
        private_write(self.wizard.pin, "sha256:" + "c" * 64)
        with (patch.object(gateway_docker, "command") as docker,
              self.assertRaisesRegex(ConfigError, "different executor image")):
            self.wizard.prepare_image(self.metadata)
        docker.assert_not_called()

    def test_executor_paths_cannot_reach_gateway_files_or_maintenance_backups(self):
        with self.setup_environment(self.first_setup("later")):
            self.wizard.setup()
        original = json.loads(self.wizard.config.read_text())
        alias = self.wizard.config.parent / "credential-alias"
        alias.symlink_to(self.wizard.gateway_dir / "ibc.ini")
        for field in ("token_path", "journal_path", "ca_file"):
            for path in (self.wizard.gateway_dir / "ibc.ini", alias,
                         self.wizard.state / "maintenance/old/config/gateway/ibc.ini"):
                with self.subTest(field=field, path=path):
                    private_write(self.wizard.config, json.dumps(original | {field: str(path)}))
                    with self.assertRaisesRegex(ConfigError, "private to the host"):
                        self.wizard.current_config()

    def test_bad_image_checksum_blocks_docker_load(self):
        archive = self.release / "images/executor.tar.gz"
        archive.parent.mkdir()
        archive.write_bytes(b"damaged archive")
        with (patch.object(gateway_docker, "command", side_effect=gateway_docker.DockerUnavailable("missing")) as docker,
              self.assertRaisesRegex(ConfigError, "checksum failed")):
            self.wizard.prepare_image(self.metadata)
        self.assertEqual(docker.call_count, 1)

    def test_running_or_enabled_executor_and_cli_lock_block_setup(self):
        with (patch.object(stack, "service_state", return_value="active"),
              self.assertRaisesRegex(ConfigError, "executor is running")):
            self.wizard.require_idle()
        with (patch.object(stack, "service_state", return_value="inactive"),
              patch.object(stack.subprocess, "run", return_value=Mock(returncode=0)),
              self.assertRaisesRegex(ConfigError, "automatic startup")):
            self.wizard.require_idle()
        with (patch.object(stack, "service_state", return_value="inactive"),
              patch.object(stack.subprocess, "run", return_value=Mock(returncode=1)),
              exclusive(self.wizard.config.with_suffix(".json.lock")),
              self.assertRaisesRegex(ConfigError, "running")):
            self.wizard.require_idle()

    def test_missing_docker_pauses_after_install_without_reboot_or_trading(self):
        with self.setup_environment(["y"]) as output, patch.object(stack.shutil, "which", return_value=None), \
                patch.object(stack, "command", return_value=Mock(stdout="")) as command:
            self.assertEqual(self.wizard.setup(), 3)
        mutations = [call.args[0] for call in command.call_args_list if "systemctl" not in call.args[0]]
        self.assertEqual(mutations, [[str(self.release / "scripts/install-docker.sh")]])
        self.assertIn("Reboot during a maintenance window", output.getvalue())
        self.assertEqual(self.calls, [])

    def test_partial_docker_install_can_finish_permissions_without_trading(self):
        with self.setup_environment(["y"]) as output, \
                patch.object(stack, "docker_group_configured", return_value=False), \
                patch.object(stack, "local_docker_package", return_value=True), \
                patch.object(stack, "command", return_value=Mock(stdout="")) as command:
            self.assertEqual(self.wizard.setup(), 3)
        mutations = [call.args[0] for call in command.call_args_list if "systemctl" not in call.args[0]]
        self.assertEqual(mutations, [[str(self.release / "scripts/install-docker.sh")]])
        self.assertIn("permissions saved. Reboot", output.getvalue())
        self.assertEqual(self.calls, [])

    def test_permission_repair_can_be_declined_and_does_not_replace_an_unknown_runtime(self):
        with self.setup_environment(["n"]), \
                patch.object(stack, "docker_group_configured", return_value=False), \
                patch.object(stack, "local_docker_package", return_value=True), \
                patch.object(stack, "command", return_value=Mock(stdout="")) as command:
            self.assertEqual(self.wizard.setup(), 3)
        self.assertFalse(any("install-docker.sh" in str(c.args[0]) for c in command.call_args_list))
        with self.setup_environment([]), \
                patch.object(stack, "docker_group_configured", return_value=False), \
                patch.object(stack, "local_docker_package", return_value=False), \
                self.assertRaisesRegex(ConfigError, "Review the existing runtime"):
            self.wizard.setup()

    def test_saved_docker_membership_requires_a_fresh_login_before_engine_access(self):
        with patch.object(stack, "docker_group_configured", return_value=True), \
                patch.object(stack.grp, "getgrnam", return_value=Mock(gr_gid=984)), \
                patch.object(stack.os, "getgroups", return_value=[1000]), \
                patch.object(stack.os, "getgid", return_value=1000), \
                patch.object(gateway_docker, "require_engine") as engine, \
                self.assertRaisesRegex(ConfigError, "login has not refreshed"):
            stack.docker_access()
        engine.assert_not_called()

    def test_doctor_does_not_change_services_and_forwarded_options_survive(self):
        with self.setup_environment([]), patch.object(stack, "Stack", return_value=self.wizard):
            self.assertEqual(stack.main(self.release, ["doctor"]), 0)
            self.assertEqual(stack.main(self.release, ["settings", "--root", "NQ", "--quantity", "2"]), 0)
        self.assertEqual(self.gateway_commands, [])
        self.assertEqual(self.calls, [("settings", ("--root", "NQ", "--quantity", "2"))])

    def test_no_private_prompt_in_noninteractive_session(self):
        output = io.StringIO()
        with patch.object(stack.sys.stdin, "isatty", return_value=False), contextlib.redirect_stderr(output):
            self.assertEqual(stack.main(self.release, ["setup"]), 2)
        self.assertIn("own terminal", output.getvalue())
        self.assertFalse(self.wizard.config.exists())

    def test_user_manager_needs_docker_group_even_if_shell_has_access(self):
        with (patch.object(gateway_docker, "require_engine"),
              patch.object(gateway_docker, "command", return_value=Mock(stdout='["name=seccomp"]')),
              patch.object(stack, "command", return_value=Mock(stdout="1234")),
              patch.object(Path, "stat", return_value=Mock(st_gid=984)),
              patch.object(Path, "read_text", return_value="Name:\tsystemd\nGroups:\t1001 27\n"),
              self.assertRaisesRegex(ConfigError, "Reboot during a maintenance window")):
            stack.docker_access()

    def test_rootless_docker_is_refused(self):
        with (patch.object(gateway_docker, "require_engine"),
              patch.object(gateway_docker, "command", return_value=Mock(stdout='["name=rootless"]')),
              self.assertRaisesRegex(ConfigError, "rootful")):
            stack.docker_access()


if __name__ == "__main__":
    unittest.main()
