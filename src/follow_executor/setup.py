# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Follower setup and verified, flat-only changes of sizing, instrument and size."""

from __future__ import annotations

import getpass
import json
import math
import os
from pathlib import Path

from .config import ConfigError, ExecutorConfig, load_config, parse_config
from .journal import Journal
from .local import (
    bind_settings,
    default_state_path,
    exclusive,
    private_write,
    settings_identity,
)
from .sizing import preview_text

DEFAULT_RELAY = "https://relay.quantmnq.com"
DEFAULT_STREAM = "sessioncycle.mnq"
DEFAULT_KEY = "zesvLFF3vT/hPtfal4i+m6K35v+cO9x4+jOXFLH6Xp4="


def ask(label: str, default: str = "", choices: tuple[str, ...] = ()) -> str:
    while True:
        answer = input(f"{label}{f' [{default}]' if default else ''}: ").strip() or default
        if answer and (not choices or answer in choices):
            return answer
        print(f"Enter {' / '.join(choices) if choices else 'a value'}.")


def ask_quantity(default: int, ceiling: int) -> int:
    while True:
        value = ask(f"Number of contracts (1–{ceiling})", str(default))
        if value.isdecimal() and 1 <= int(value) <= ceiling:
            return int(value)
        print(f"Enter a whole number from 1 to {ceiling}.")


def ask_fraction(default: float | None = None) -> float:
    while True:
        value = ask("Leverage fraction of the leader's 6x band (above 0, at most 1)",
                    "" if default is None else f"{default:g}")
        try:
            fraction = float(value)
        except ValueError:
            fraction = math.nan
        if math.isfinite(fraction) and 0 < fraction <= 1:
            return fraction
        print("Enter a number above 0 and at most 1, such as 0.5. 1 follows the leader's full 6x.")


def ask_amount(label: str) -> float | None:
    while True:
        value = input(f"{label} (Enter to skip): ").strip().replace(",", "").removeprefix("$")
        if not value:
            return None
        try:
            amount = float(value)
        except ValueError:
            amount = math.nan
        if math.isfinite(amount) and amount > 0:
            return amount
        print("Enter a positive number, or press Enter to skip.")


def show_preview(fraction: float, max_quantity: int, equity: float | None = None) -> None:
    """Show the NQ/MNQ split at example weights; ask only for what IBKR has not supplied."""

    if equity is None:
        equity = ask_amount("Your current IBKR NetLiquidation in USD, for a size preview")
    else:
        print(f"IBKR NetLiquidation: ${equity:,.2f}")
    price = None if equity is None else ask_amount("Approximate current NQ price, for the preview")
    if equity is None or price is None:
        print("Preview skipped. The readiness check shows it from IBKR.")
        return
    print(preview_text(fraction, equity, price, max_quantity))


def describe(config: ExecutorConfig) -> str:
    if config.sizing is not None:
        return f"NQ + MNQ balance sizing at leverage fraction {config.sizing.leverage_fraction:g}"
    return f"{config.quantity} {config.root}"


def ask_sizing(default: str) -> str:
    print("Sizing: 'balance' trades NQ plus an MNQ remainder sized from your NetLiquidation")
    print("at each new entry; 'MNQ' or 'NQ' trades a fixed number of that contract.")
    return ask("Sizing", default, ("balance", "MNQ", "NQ"))


def initial_config(path: Path, *, advanced: bool = False) -> int:
    if path.exists():
        current = load_config(path)
        print(f"Existing {current.ibkr.account_type} setup: {describe(current)}.")
        choice = ask_sizing("balance" if current.sizing else current.root)
        if choice == "balance":
            fraction = ask_fraction(current.sizing.leverage_fraction if current.sizing else None)
            return change_settings(path, fraction=fraction, interactive=True)
        quantity = ask_quantity(current.quantity or 1, current.max_quantity)
        return change_settings(path, root=choice, quantity=quantity)

    print("Follow Executor setup — IBKR passwords stay in Gateway/IBC on your VM.")
    mode = ask("Account mode", "paper", ("paper", "live"))
    account = ask("IBKR account ID (for example DU1234567)").upper()
    fraction = root = quantity = None
    choice = ask_sizing("balance")
    if choice == "balance":
        fraction = ask_fraction()
        show_preview(fraction, 10)
    else:
        root = choice
        quantity = ask_quantity(1, 10)
    if mode == "live" and input(
        f"Type LIVE {account} to configure real-money trading: "
    ).strip() != f"LIVE {account}":
        raise ConfigError("live setup cancelled; no files changed")
    raw = {
        "relay_url": DEFAULT_RELAY,
        "stream": DEFAULT_STREAM,
        "leader_public_key": DEFAULT_KEY,
        "token_path": str(path.parent / "relay.token"),
        "journal_path": str(default_state_path()),
        "ibkr": {
            "host": "127.0.0.1", "port": 4002 if mode == "paper" else 4001,
            "client_id": 71, "account": account, "account_type": mode,
        },
        **({"sizing": {"mode": "balance", "leverage_fraction": fraction}} if fraction is not None
           else {"instrument": {"root": root, "quantity": quantity}}),
        "risk": {"max_quantity": 10, "max_margin_fraction": 0.5,
                 "max_entry_slippage_points": 10, "max_stop_risk_usd": None},
        "feed": {"send_acks": True},
    }
    if advanced:
        raw["relay_url"] = ask("Relay URL", DEFAULT_RELAY)
        raw["stream"] = ask("Stream", DEFAULT_STREAM)
        raw["leader_public_key"] = ask("Leader public key", DEFAULT_KEY)
        raw["ibkr"]["host"] = ask("IB Gateway host", "127.0.0.1")
        raw["ibkr"]["port"] = int(ask("IB Gateway API port", str(raw["ibkr"]["port"])))
        raw["ibkr"]["client_id"] = int(ask("IB Gateway client ID", "71"))
    config = parse_config(raw)
    token = getpass.getpass("Personal relay token (hidden): ").strip()
    if not token or any(c.isspace() for c in token):
        raise ConfigError("a nonempty relay token without whitespace is required")
    with exclusive(config.journal_path.with_suffix(config.journal_path.suffix + ".lock")):
        journal = Journal(config.journal_path)
        try:
            bind_settings(journal, config)
        finally:
            journal.close()
        private_write(config.token_path, token + "\n")
        private_write(path, json.dumps(raw, indent=2) + "\n")
    print(f"Saved {describe(config)} in {mode} mode to {path}.")
    launcher = os.environ.get("FOLLOW_EXECUTOR_LAUNCHER", "./follow")
    print(f"Log in to IB Gateway, then run '{launcher} check' and '{launcher} start'.")
    return 0


def require_flat(config: ExecutorConfig, *, roots: tuple[str, ...] | None = None) -> float | None:
    """Wait for IBKR snapshot-end callbacks; an empty early cache is not proof.

    Returns NetLiquidation for a size preview when IBKR reports it.
    """
    from .ibkr import IBKRBroker

    roots = config.roots if roots is None else roots
    broker = IBKRBroker(config.ibkr, roots)
    try:
        broker.connect()
        if config.ibkr.account not in broker.managed_accounts:
            raise ConfigError("the configured account is not managed by this Gateway login")
        broker.refresh()
        broker.wait_for_snapshot()
        state = broker.state()
        if any(state.positions.values()) or any(o.working for o in state.orders.values()):
            raise ConfigError(
                f"{'/'.join(roots)} has positions or working orders; settings were not changed. "
                "Wait until flat and all orders are completed/cancelled."
            )
        try:
            return broker.net_liquidation()
        except Exception:  # noqa: BLE001 - the preview then asks for the balance
            return None
    finally:
        broker.disconnect()


def change_settings(path: Path, *, root: str | None = None, quantity: int | None = None,
                    fraction: float | None = None, interactive: bool = False) -> int:
    old = load_config(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if fraction is not None:
        if root is not None or quantity is not None:
            raise ConfigError("balance sizing chooses NQ and MNQ quantities; omit --root and --quantity")
        raw.pop("instrument", None)
        raw["sizing"] = {"mode": "balance", "leverage_fraction": fraction}
    else:
        if old.sizing is not None and (root is None or quantity is None):
            raise ConfigError("leaving balance sizing needs both --root and --quantity")
        raw.pop("sizing", None)
        raw["instrument"] = {"root": root or old.root,
                             "quantity": old.quantity if quantity is None else quantity}
    new = parse_config(raw)
    if settings_identity(new) == settings_identity(old):
        print(f"Already configured for {describe(old)}; no changes.")
        return 0
    with exclusive(old.journal_path.with_suffix(old.journal_path.suffix + ".lock")):
        journal = Journal(old.journal_path)
        try:
            bind_settings(journal, old)
            if journal.expected_positions():
                raise ConfigError("the journal records an open position; wait until flat")
            if journal.halt_reason():
                raise ConfigError("resolve the executor halt before changing settings")
            # Check the full old/new scope with one connection. Reconnecting
            # immediately with the same client ID can race Gateway's disconnect.
            roots = tuple(dict.fromkeys((*old.roots, *new.roots)))
            equity = require_flat(old, roots=roots)
            if new.sizing is not None:
                equity = equity if isinstance(equity, (int, float)) else None
                if interactive:
                    show_preview(new.sizing.leverage_fraction, new.max_quantity, equity)
            # Preserve trade history: changing size must never re-enter a finished trade.
            private_write(path, json.dumps(raw, indent=2) + "\n")
            journal.set_state("settings_identity", settings_identity(new))
            journal.log("settings_changed", {"root": new.root, "quantity": new.quantity,
                                             "leverage_fraction": new.sizing.leverage_fraction
                                             if new.sizing else None})
        finally:
            journal.close()
    launcher = os.environ.get("FOLLOW_EXECUTOR_LAUNCHER", "./follow")
    print(f"Saved {describe(new)}. Run '{launcher} check', then '{launcher} start' to apply it.")
    return 0
