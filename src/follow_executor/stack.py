# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Resumable container onboarding using only the host Python standard library."""

from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import platform
import pwd
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from . import gateway, gateway_docker
from .config import ConfigError, load_config
from .local import exclusive, private_write


def command(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, text=True, capture_output=capture, check=False)
    if result.returncode:
        raise ConfigError(f"{Path(args[0]).name} failed (exit {result.returncode})")
    return result


def host_check() -> None:
    if os.getuid() == 0:
        raise ConfigError("Run as your Ubuntu login user, without sudo.")
    release = platform.freedesktop_os_release()
    if (platform.system() != "Linux" or platform.machine() != "aarch64"
            or release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04"):
        raise ConfigError("The container wizard supports Ubuntu 24.04 ARM64.")


def service_state(name: str, *, user: bool = True) -> str:
    return command(["systemctl", *(["--user"] if user else []), "show", name,
                    "-p", "ActiveState", "--value"]).stdout.strip()


def docker_group_configured() -> bool:
    try:
        group = grp.getgrnam("docker")
        return os.getgid() == group.gr_gid or pwd.getpwuid(os.getuid()).pw_name in group.gr_mem
    except KeyError:
        return False


def local_docker_package() -> bool:
    result = subprocess.run(["dpkg-query", "-W", "-f=${Status}", "docker-ce"],
                            text=True, capture_output=True, check=False)
    return result.returncode == 0 and result.stdout.strip() == "install ok installed"


def docker_access() -> None:
    if docker_group_configured() and grp.getgrnam("docker").gr_gid not in (*os.getgroups(), os.getgid()):
        raise ConfigError("Docker group membership is saved but this login has not refreshed. "
                          "Reboot during a maintenance window, reconnect and rerun './follow-stack setup'.")
    gateway_docker.require_engine()
    security = json.loads(gateway_docker.command(["info", "--format", "{{json .SecurityOptions}}"]).stdout)
    if any("rootless" in option or "userns" in option for option in security):
        raise ConfigError("Use the local rootful Docker engine without user-namespace remapping.")
    # A fresh SSH shell can have Docker access while its user manager still cannot.
    pid = int(command(["systemctl", "show", f"user@{os.getuid()}.service",
                       "-p", "MainPID", "--value"]).stdout.strip())
    status = Path(f"/proc/{pid}/status").read_text()
    groups = next(line.split()[1:] for line in status.splitlines() if line.startswith("Groups:"))
    gid = str(Path("/var/run/docker.sock").stat().st_gid)
    if gid not in groups:
        raise ConfigError("The user service manager lacks Docker group access. Reboot during a maintenance "
                          "window, reconnect, and rerun './follow-stack setup'. No reboot was requested.")


def lingering() -> bool:
    return command(["loginctl", "show-user", str(os.getuid()), "-p", "Linger", "--value"]).stdout.strip() == "yes"


class Stack:
    def __init__(self, release: Path):
        self.release = gateway.safe_path(str(release))
        self.launcher = self.release / "follow-stack"
        bases = [os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")),
                 os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))]
        if any(not value.startswith("/") or "," in value for value in bases):
            raise ConfigError("XDG directories must be absolute paths without commas.")
        self.config_base, self.state_base = (gateway.safe_path(value) for value in bases)
        self.config = self.config_base / "follow-executor/executor.json"
        self.state = self.state_base / "follow-executor"
        self.gateway_dir = self.config.parent / "gateway"
        self.pin = self.state / "container.image"
        identity = hashlib.sha256(str(self.config).encode()).hexdigest()[:12]
        self.unit = f"follow-executor-container-{identity}.service"
        self.unit_path = self.config_base / "systemd/user" / self.unit
        self.gateway_unit = Path.home() / ".config/systemd/user" / gateway.SERVICE

    def invoke(self, action: str, *options: str) -> int:
        env = dict(os.environ, DOCKER_HOST="unix:///var/run/docker.sock",
                   XDG_CONFIG_HOME=str(self.config_base), XDG_STATE_HOME=str(self.state_base),
                   FOLLOW_EXECUTOR_LAUNCHER="./follow-stack", FOLLOW_CHECK_QUOTES="1")
        for key in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
            env.pop(key, None)
        return subprocess.run([str(self.release / "follow-container"), action, *options],
                              env=env, check=False).returncode

    def invoke_required(self, action: str, *options: str) -> None:
        if self.invoke(action, *options):
            raise ConfigError(f"'{action}' did not complete. Resolve the reported problem and rerun setup.")

    def maintenance_report(self, image_id: str) -> dict:
        env = dict(os.environ, DOCKER_HOST="unix:///var/run/docker.sock", FOLLOW_EXECUTOR_PROBE_IMAGE=image_id,
                   XDG_CONFIG_HOME=str(self.config_base), XDG_STATE_HOME=str(self.state_base))
        for key in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
            env.pop(key, None)
        result = subprocess.run([str(self.release / "follow-container"), "maintenance-check"],
                                env=env, text=True, capture_output=True, check=False)
        if result.returncode:
            raise ConfigError("Maintenance check failed. Verify account access, complete snapshots, no blocking positions and no working orders; "
                              "no services were changed. The journal may retain an existing halt.")
        return json.loads(result.stdout)

    def install_image(self, image_id: str) -> None:
        previous = os.environ.get("FOLLOW_EXECUTOR_IMAGE")
        try:
            os.environ["FOLLOW_EXECUTOR_IMAGE"] = image_id
            self.invoke_required("install")
        finally:
            if previous is None:
                os.environ.pop("FOLLOW_EXECUTOR_IMAGE", None)
            else:
                os.environ["FOLLOW_EXECUTOR_IMAGE"] = previous

    def require_idle(self) -> None:
        services = (("follow-executor.service", False), ("follow-executor.service", True), (self.unit, True))
        for name, user in services:
            if service_state(name, user=user) not in ("inactive", "failed"):
                raise ConfigError("An executor is running. Use an agreed flat-account maintenance window "
                                  "before setup; the wizard will not stop trading.")
        for name, user in services:
            enabled = subprocess.run(["systemctl", *(["--user"] if user else []),
                                      "is-enabled", "--quiet", name], check=False)
            if enabled.returncode == 0:
                raise ConfigError("An executor is enabled for automatic startup. Stop and disable it explicitly "
                                  "while flat before rerunning setup.")
        # Also detect CLI processes which are not managed by systemd.
        with exclusive(self.config.with_suffix(".json.lock")):
            if self.config.exists():
                current = self.current_config()
                with exclusive(current.journal_path.with_suffix(current.journal_path.suffix + ".lock")):
                    pass

    def require_gateway_ownership(self) -> None:
        fragment = command(["systemctl", "--user", "show", gateway.SERVICE,
                            "-p", "FragmentPath", "--value"]).stdout.strip()
        paths = {self.gateway_unit}
        if fragment:
            paths.add(Path(fragment))
        expected = f'ExecStart="{self.launcher}" gateway --config "{self.config}" run'
        for path in paths:
            if path.exists() and expected not in path.read_text().splitlines():
                raise ConfigError("An existing Gateway service belongs to another installation. "
                                  "Use a reviewed migration while flat; setup will not replace that service.")
        if service_state(gateway.SERVICE) not in ("inactive", "failed") and not self.gateway_unit.exists():
            raise ConfigError("A Gateway service is running without this wizard's unit. Review it before setup.")

    def current_config(self):
        current = load_config(self.config)
        if current.ibkr.host != "127.0.0.1":
            raise ConfigError("The combined setup requires Gateway on 127.0.0.1.")
        for path in (current.token_path, current.journal_path, current.ca_file):
            if path and (any(path.resolve().is_relative_to(base) for base in
                             (self.gateway_dir, self.state / "maintenance"))
                         or not any(path.resolve().is_relative_to(base) for base in (self.config.parent, self.state))):
                raise ConfigError("Existing token, journal or CA paths are outside the container mounts. "
                                  "Gateway and maintenance-backup directories are private to the host. "
                                  "Review migration without moving or resetting trading history.")
        return current

    def image_metadata(self) -> dict:
        path = self.release / "RELEASE.json"
        metadata = json.loads(path.read_text()) if path.exists() else {}
        image = metadata.get("executor_image", {})
        if (not re.fullmatch(r"sha256:[a-f0-9]{64}", image.get("id", ""))
                or image.get("platform") != "linux/arm64"
                or image.get("wheel_sha256") != metadata.get("wheel_sha256")):
            raise ConfigError("Use the combined container customer kit, which includes its verified executor image. "
                              "Maintainers: see docs/CONTAINER_SETUP.md.")
        return image

    def prepare_image(self, image: dict, *, changing: bool = False) -> None:
        if not changing and self.pin.exists() and self.pin.read_text().strip() != image["id"]:
            raise ConfigError("A different executor image is installed. Use the reviewed upgrade procedure; "
                              "setup does not change an installed image.")
        try:
            gateway_docker.command(["image", "inspect", "--format", "{{.Id}}", image["id"]])
        except gateway_docker.DockerUnavailable:
            archive = (self.release / image["archive"]).resolve()
            if not archive.is_relative_to(self.release):
                raise ConfigError("Invalid image archive path.")
            with archive.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if digest != image["archive_sha256"]:
                raise ConfigError("Executor image checksum failed. Obtain the original customer archive.")
            print("Loading the verified executor image; this does not start it.", flush=True)
            gateway_docker.command(["load", "--input", str(archive)], capture=False, timeout=300)
        actual = gateway_docker.command(["image", "inspect", "--format",
                                         "{{.Id}} {{.Os}}/{{.Architecture}}", image["id"]]).stdout.strip()
        if actual != f"{image['id']} linux/arm64":
            raise ConfigError("The loaded executor image does not match this release.")

    def gateway_action(self, action: str, *, vnc: bool | None = None) -> int:
        self.require_gateway_ownership()
        if action != "container-stop" and (self.gateway_dir / "gateway.json").exists():
            # Deliberate reconfiguration can repair an interrupted credential save;
            # runtime/start still require the complete, consistent saved settings.
            settings = gateway.load_settings(self.gateway_dir, check_consistency=action != "configure")
            if settings.get("backend") != "docker":
                raise ConfigError("Existing native Gateway settings need a reviewed migration.")
        result = gateway.dispatch(self.config, action, backend="docker" if action == "configure" else None,
                                  vnc=vnc, launcher=self.launcher)
        if result == 0 and action in ("configure", "refresh"):
            private_write(self.gateway_unit, self.gateway_unit_text(gateway.load_settings(self.gateway_dir)))
            command(["systemctl", "--user", "daemon-reload"])
        return result

    def gateway_unit_text(self, settings: dict) -> str:
        text = gateway.unit_text(self.config, self.release, settings["timezone"], "docker", launcher=self.launcher)
        # The supervisor must see the same pending-maintenance marker even when
        # the operator uses custom XDG paths absent from the user manager's env.
        environment = (f'Environment="XDG_CONFIG_HOME={self.config_base}"\n'
                       f'Environment="XDG_STATE_HOME={self.state_base}"\n')
        return text.replace("[Service]\n", "[Service]\n" + environment, 1)

    def setup(self, *, vnc: bool = True) -> int:
        print("Auto Quant container setup — rerun this command to resume.", flush=True)
        host_check()
        self.require_gateway_ownership()
        self.require_idle()
        image = self.image_metadata()
        print("1/5  Docker and startup permissions", flush=True)
        if not shutil.which("docker"):
            if input("Install Docker from its official Ubuntu repository using sudo? [y/N]: ").strip().lower() != "y":
                print("Paused. Install Docker, then rerun './follow-stack setup'.")
                return 3
            command([str(self.release / "scripts/install-docker.sh")], capture=False)
            print("Docker installed. Reboot during a maintenance window, reconnect and rerun './follow-stack setup'.")
            return 3
        if not docker_group_configured():
            if not local_docker_package():
                raise ConfigError("Docker permissions are incomplete and the supported local Docker Engine package "
                                  "is not installed. Review the existing runtime before continuing.")
            print("Docker is installed, but this login's Docker group setup is incomplete.")
            if input("Finish local Docker startup permissions using sudo? [y/N]: ").strip().lower() != "y":
                print("Paused. Rerun './follow-stack setup' to finish Docker permissions.")
                return 3
            command([str(self.release / "scripts/install-docker.sh")], capture=False)
            print("Docker permissions saved. Reboot during a maintenance window, reconnect and rerun './follow-stack setup'.")
            return 3
        docker_access()
        if not lingering():
            if input("Enable services after logout and reboot using sudo? [y/N]: ").strip().lower() != "y":
                print("Paused. Run 'sudo loginctl enable-linger $USER', then rerun setup.")
                return 3
            command(["sudo", "loginctl", "enable-linger", str(os.getuid())], capture=False)
            if not lingering():
                raise ConfigError("User lingering is still disabled; run './follow-stack doctor'.")

        print("2/5  Verified executor image and stopped service", flush=True)
        self.prepare_image(image)
        # An interrupted install can leave either the pin or unit missing. Reinstall
        # the SAME verified image while stopped; never reset configuration or state.
        self.install_image(image["id"])

        print("3/5  Account and personal relay access", flush=True)
        if not self.config.exists():
            self.invoke_required("configure")
        current = self.current_config()
        print(f"Saved setup: {current.ibkr.account_type}, {current.size_label}. Credentials stay private.")

        print("4/5  Gateway login", flush=True)
        if not (self.gateway_dir / "gateway.json").exists():
            self.gateway_action("configure", vnc=vnc)
        settings = gateway.load_settings(self.gateway_dir)
        if (settings["mode"], settings["port"]) != (current.ibkr.account_type, current.ibkr.port):
            raise ConfigError("Gateway mode/port differs from the executor. Review saved settings before continuing.")
        if not self.gateway_unit.exists():
            self.gateway_action("refresh")
        self.gateway_action("start")
        print("Approve the expected IBKR Mobile prompt and finish any Gateway notices.")
        if settings.get("vnc"):
            print("On your computer: ssh -i YOUR_KEY -N -L 5901:127.0.0.1:5901 YOUR_USER@YOUR_VM")
            print("Then open your VNC viewer at localhost:5901 (TigerVNC: localhost::5901).")
        if input("After login, press Enter to check readiness, or type later to pause: ").strip():
            print("Saved. Gateway stays available for login. Resume with './follow-stack setup'. Trading is stopped.")
            return 3
        print("5/5  Relay, account, journal and margin checks", flush=True)
        result = self.invoke("check", "--quotes")
        if result:
            print("Readiness checks did not pass. Resolve the reported issue, then rerun './follow-stack setup'.")
            print("For a login dialog use the private VNC screen. Trading has not been started.")
            return result
        print("Setup checks passed, including a live quote for the selected contract.")
        print(f"Review {current.ibkr.account_type}, {current.size_label}; then explicitly run './follow-stack start'.")
        print("Trading is stopped. Optional notifications: ./follow-stack discord link")
        return 0

    def start(self) -> int:
        host_check()
        docker_access()
        self.require_gateway_ownership()
        self.require_idle()
        if not lingering():
            raise ConfigError("Run setup to enable services after logout and reboot.")
        if not self.pin.exists() or not self.unit_path.exists() or not self.gateway_unit.exists():
            raise ConfigError("Run './follow-stack setup' first.")
        if self.pin.read_text().strip() != self.image_metadata()["id"]:
            raise ConfigError("Installed executor image differs from this release; review the upgrade.")
        current = self.current_config()
        confirmation = f"START {current.ibkr.account_type.upper()} {current.size_label}"
        print("Starting will check readiness, enable automatic recovery and begin following trading signals.")
        if input(f"Type {confirmation} to continue: ").strip() != confirmation:
            print("Cancelled. No trading start requested.")
            return 3
        return self.invoke("start")

    def doctor(self) -> int:
        host_check()
        print("Host: Ubuntu 24.04 ARM64; standard-library controller available.")
        docker_access()
        print("Docker: local engine and user service permissions ready.")
        print(f"Startup after logout/reboot: {'enabled' if lingering() else 'needs setup'}")
        print(f"Executor configuration: {'saved' if self.config.exists() else 'needs setup'}")
        print(f"Executor service: {service_state(self.unit)}")
        print(f"Gateway service: {service_state(gateway.SERVICE)} (process state, not login readiness)")
        print("Continue setup: ./follow-stack setup; check broker/relay while stopped: ./follow-stack check")
        return 0


def main(release: Path, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="follow-stack", description="Set up Gateway and executor containers; setup never starts trading.")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup", help="resume private setup and readiness checks")
    setup.add_argument("--no-vnc", action="store_true", help="disable recovery desktop for a new setup")
    commands.add_parser("doctor", help="check host, permissions and saved setup without changing services")
    commands.add_parser("start", help="explicitly confirm trading, then check and start")
    upgrade = commands.add_parser("upgrade", help="switch compatible releases while flat; leave both services stopped")
    upgrade.add_argument("--from", dest="source", type=Path, required=True, help="retained installed release directory")
    commands.add_parser("rollback", help="restore the previous compatible release without restoring old trading history")
    gw = commands.add_parser("gateway", help="manage Gateway login and private recovery")
    gw.add_argument("--config", type=Path, help=argparse.SUPPRESS)
    gw.add_argument("action", choices=("configure", "start", "stop", "status", "logs", "refresh", "run", "container-stop"))
    gw.add_argument("--vnc", action=argparse.BooleanOptionalAction, default=None)
    delegated = ("check", "stop", "status", "service-status", "logs", "settings", "discord", "watch", "resume")
    for name in delegated:
        commands.add_parser(name, help=f"executor {name}", add_help=False)
    args, options = parser.parse_known_args(argv)
    if options and args.command not in delegated:
        parser.error("unrecognized arguments: " + " ".join(options))
    os.umask(0o077)
    try:
        if ((args.command in ("setup", "start", "upgrade", "rollback") or args.command == "gateway" and args.action == "configure")
                and not sys.stdin.isatty()):
            raise ConfigError("Run this interactive command in your own terminal. Keep credentials out of chat.")
        stack = Stack(release)
        from .maintenance import require_complete, switch

        if args.command in ("setup", "start") or args.command == "gateway" and args.action in ("configure", "start", "run", "refresh"):
            require_complete(stack)
        if args.command in ("upgrade", "rollback"):
            with exclusive(stack.state / "stack-setup.lock"):
                return switch(stack, args.source if args.command == "upgrade" else None, rollback=args.command == "rollback")
        if args.command == "gateway":
            if args.config:
                # Absolute identity is embedded in the supervisor unit, independent
                # of the user manager's XDG environment.
                stack.config = gateway.safe_path(str(args.config))
                stack.gateway_dir = stack.config.parent / "gateway"
            return stack.gateway_action(args.action, vnc=args.vnc)
        if args.command in ("setup", "start"):
            with exclusive(stack.state / "stack-setup.lock"):
                return stack.setup(vnc=not args.no_vnc) if args.command == "setup" else stack.start()
        if args.command == "doctor":
            return stack.doctor()
        if args.command == "check":
            print(f"Gateway process: {service_state(gateway.SERVICE)} (account and quotes checked below).", flush=True)
            if "--skip-broker" not in options:
                return stack.invoke("check", "--quotes", *options)
        return stack.invoke(args.command, *options)
    except (ConfigError, OSError, ValueError, RuntimeError, KeyError, sqlite3.Error) as exc:
        print(f"follow-stack: {exc}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        next_step = "rollback" if args.command in ("upgrade", "rollback") else "setup"
        print(f"Paused. Saved configuration is retained; use './follow-stack {next_step}' to recover.", file=sys.stderr)
        return 130
