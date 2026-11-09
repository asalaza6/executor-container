# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""follow-executor: check, watch, run, status and resume."""

from __future__ import annotations

import argparse
import email.utils
import json
import logging
import os
import signal
import sqlite3
import ssl
import sys
import threading
import time
import urllib.request
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from follow_executor.crypto import Verifier

from .broker import MULTIPLIERS, OrderRequest
from .config import ConfigError, ExecutorConfig, load_config
from .journal import Journal
from .local import bind_settings, default_config_path, exclusive
from .signal import SignalError, parse_target
from .sizing import book_label, preview

LOGGER = logging.getLogger("follow_executor")


def _verifier(config: ExecutorConfig) -> Verifier:
    return Verifier(config.leader_public_key)


def _context(config: ExecutorConfig) -> ssl.SSLContext | None:
    if not config.relay_url.startswith("https"):
        return None
    return ssl.create_default_context(cafile=str(config.ca_file) if config.ca_file else None)


def _describe(target: Any) -> dict[str, Any]:
    return {
        "seq": target.seq,
        "cause": target.cause,
        "emitted_at": target.emitted_at.isoformat(),
        "position": target.position,
        "leg": target.leg,
        "contract_month": target.contract_month,
        "stop": target.stop,
        "entry_deadline": None if target.entry is None else target.entry.deadline.isoformat(),
        "exit_rule": None if target.exit_plan is None else target.exit_plan.rule,
        "sizing": None if target.sizing is None else {
            "weight": target.sizing.weight, "target_leverage": target.sizing.target_leverage,
            "add_max_leverage": target.sizing.add_max_leverage,
            "hold_max_leverage": target.sizing.hold_max_leverage,
        },
    }


def _book(config: ExecutorConfig, journal: Journal) -> str:
    """Expected position by root, such as ``1 NQ + 5 MNQ``."""
    roots = json.loads(journal.get_state("contract_roots") or "{}")
    quantities: dict[str, int] = {}
    for con_id, quantity in journal.expected_positions().items():
        root = roots.get(str(con_id), config.root)
        quantities[root] = quantities.get(root, 0) + quantity
    return book_label(quantities)


def balance_preview(config: ExecutorConfig, equity: float, price: float, source: str) -> dict:
    assert config.sizing is not None
    base, sizes = preview(config.sizing.leverage_fraction, equity, price)
    return {
        "net_liquidation": equity, "nq_price": price, "price_source": source, "base_units": base,
        "weights": [{"weight": size.weight, "units": size.units, "NQ": size.nq, "MNQ": size.mnq,
                     "book": size.book} for size in sizes],
    }


def quote_readiness(broker, contract, timeout: float) -> dict:
    contracts = contract if isinstance(contract, list) else [contract]
    broker.monitor_market_data(contracts)
    deadline = time.monotonic() + min(timeout, 10)
    while True:
        health = broker.health()
        status = health["market_data"]
        if not health["connected"]:
            status = "disconnected"
        if status not in ("pending", "idle") or time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    codes = broker.market_data_errors()
    if 10197 in codes and status != "ready":
        note = "A competing live session is using market data. Log out of that session deliberately, then retry."
    elif status == "ready":
        note = "A live bid, ask or last price was received for the selected contract."
    elif status == "denied" and 354 in codes:
        note = ("IBKR error 354: the requested live market data is not subscribed. "
                "Check Market Data Subscriptions in IBKR Client Portal for the Gateway login username "
                "and API access to the selected contract, then retry. Trading permissions and margin "
                "approval do not provide market-data access.")
    elif status in ("pending", "idle"):
        status = "no_quote"
        note = "No live quote arrived before the timeout. The market may be closed; retry when live quotes are available."
    elif status == "delayed":
        note = "Only delayed or frozen data is available. Check live market-data permissions and retry."
    else:
        note = "Live market data is unavailable. Check Gateway login, connectivity and market-data permissions, then retry."
    return {"status": status, "codes": codes, "message": note}


def command_check(config: ExecutorConfig, *, skip_broker: bool, quotes: bool = False) -> int:
    report: dict[str, Any] = {"account_type": config.ibkr.account_type, "root": config.root,
                              "quantity": config.quantity}
    if config.sizing is not None:
        report.update(root="+".join(config.roots), quantity=None, sizing={
            "mode": config.sizing.mode, "leverage_fraction": config.sizing.leverage_fraction,
            "max_quantity_per_order": config.max_quantity})
    problems: list[str] = []
    readiness = {"api": "not_checked", "account": "not_checked", "reconciliation": "not_checked",
                 "market_data": {"status": "not_checked"}}
    report["readiness"] = readiness
    verifier = _verifier(config)
    report["leader_key_id"] = verifier.key_id
    latest = None
    try:
        request = urllib.request.Request(
            f"{config.relay_url}/v1/streams/{config.stream}/state",
            headers={"Authorization": f"Bearer {config.token()}"},
        )
        with urllib.request.urlopen(request, timeout=10, context=_context(config)) as response:
            body = response.read().decode()
            served = response.headers.get("Date")
        envelope = json.loads(body)
        verifier.verify(envelope)
        latest = parse_target(envelope["payload"], config.stream)
        report["relay_latest"] = _describe(latest)
        if served:
            skew = (datetime.now(UTC) - email.utils.parsedate_to_datetime(served)).total_seconds()
            report["clock_skew_seconds"] = round(skew, 1)
            if abs(skew) > 2:
                problems.append(f"local clock differs from the relay by {skew:.1f} s; enable NTP")
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        problems.append(f"relay: {type(exc).__name__}: {exc}")

    journal = Journal(config.journal_path)
    report["journal"] = {"last_seq": journal.last_seq(), "halt": journal.halt_reason(),
                         "expected_positions": journal.expected_positions(),
                         "book": _book(config, journal)}
    if journal.halt_reason():
        problems.append(f"the executor is halted: {journal.halt_reason()}")

    if not skip_broker:
        from .ibkr import IBKRBroker

        broker = None
        try:
            broker = IBKRBroker(config.ibkr, config.roots)
            readiness["api"] = "unavailable"
            broker.connect()
            readiness["api"] = "connected"
            readiness["account"] = "recognized" if config.ibkr.account in broker.managed_accounts else "not_managed"
            if config.ibkr.account not in broker.managed_accounts:
                problems.append(f"account {config.ibkr.account} is not managed by this login")
            broker.refresh()
            broker.wait_for_snapshot()
            readiness["reconciliation"] = "complete"
            if readiness["account"] == "recognized":
                readiness["account"] = "authenticated"
            state = broker.state()
            report["broker"] = {
                "positions": {k: v for k, v in state.positions.items() if v},
                "working_orders": [
                    {"order_id": o.order_id, "type": o.order_type, "ours": bool(o.purpose)}
                    for o in state.orders.values() if o.working
                ],
            }
            if {k: v for k, v in state.positions.items() if v} != journal.expected_positions():
                problems.append("broker positions differ from the executor's record; the executor would halt")
            if any(o.working and (not o.purpose or o.client_id != config.ibkr.client_id)
                   for o in state.orders.values()):
                problems.append(f"working {'/'.join(config.roots)} orders not placed by this executor")
            month = latest.contract_month if latest is not None else None
            if month and config.sizing is not None:
                _check_balance(config, broker, latest, report, readiness, problems, quotes)
            elif month:
                contract = broker.resolve(config.root, month)
                margins = {}
                for action in ("BUY", "SELL"):
                    estimate = broker.what_if(
                        OrderRequest("entry", contract, action, "MKT", config.quantity, "fx:whatif:0")
                    )
                    allowed = estimate.init_margin_after <= config.max_margin_fraction * estimate.equity_with_loan_after
                    margins[action] = {"init_margin_after": estimate.init_margin_after,
                                       "equity_with_loan_after": estimate.equity_with_loan_after,
                                       "allowed": allowed}
                    if not allowed:
                        problems.append(f"{action} {config.quantity} {config.root} would breach max_margin_fraction")
                report["contract"] = {"con_id": contract.con_id, "last_trade_date": contract.last_trade_date}
                report["margin"] = margins
                if quotes:
                    readiness["market_data"] = quote_readiness(broker, contract, config.ibkr.timeout_seconds)
                    if readiness["market_data"]["status"] != "ready":
                        problems.append(readiness["market_data"]["message"])
            elif quotes:
                readiness["market_data"] = {"status": "no_contract"}
                problems.append("Cannot verify live quotes without a contract from a verified relay state.")
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            problems.append(f"IBKR: {type(exc).__name__}: {exc}")
        finally:
            if broker is not None:
                if readiness["api"] == "connected" and not broker.is_connected:
                    problems.append("IBKR disconnected before readiness checks finished; retry after connectivity recovers.")
                    readiness["api"] = "disconnected"
                    if readiness["account"] in ("recognized", "authenticated"):
                        readiness["account"] = "unavailable"
                    readiness["reconciliation"] = "unavailable"
                broker.disconnect()
    journal.close()
    report["problems"] = problems
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if problems else 0


def _check_balance(config: ExecutorConfig, broker: Any, latest: Any, report: dict, readiness: dict,
                   problems: list[str], quotes: bool) -> None:
    """NetLiquidation, the split at example weights and the margin at weight 1, the largest size."""
    contracts = {root: broker.resolve(root, latest.contract_month) for root in config.roots}
    report["contract"] = {root: {"con_id": c.con_id, "last_trade_date": c.last_trade_date}
                          for root, c in contracts.items()}
    if quotes:
        readiness["market_data"] = quote_readiness(broker, list(contracts.values()),
                                                   config.ibkr.timeout_seconds)
        if readiness["market_data"]["status"] != "ready":
            problems.append(readiness["market_data"]["message"])
    try:
        equity = broker.net_liquidation()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        problems.append(f"NetLiquidation unavailable ({type(exc).__name__}: {exc}); balance entries "
                        "would reuse the last base or be refused")
        return
    price, source = broker.quote_price(contracts["NQ"].con_id), "live NQ quote"
    if price is None and latest.entry is not None and latest.entry.reference_price:
        price, source = latest.entry.reference_price, "latest signal reference price"
    if price is None:
        report["sizing"]["net_liquidation"] = equity
        report["sizing"]["preview"] = "needs a live NQ quote; rerun check with --quotes during market hours"
        return
    result = balance_preview(config, equity, price, source)
    report["sizing"].update(result)
    largest = result["weights"][0]
    if result["base_units"] < 1:
        problems.append("balance base is 0 MNQ units at this NetLiquidation; entries would be refused")
        return
    if largest["NQ"] > config.max_quantity:
        problems.append(f"a weight-1 trade needs {largest['NQ']} NQ, above risk.max_quantity "
                        f"{config.max_quantity}; those entries would be refused")
    margins = {}
    for action in ("BUY", "SELL"):
        estimates = [broker.what_if(OrderRequest("entry", contracts[root], action, "MKT",
                                                 largest[root], "fx:whatif:0"))
                     for root in config.roots if largest[root]]
        init_after = estimates[0].init_margin_after + sum(
            other.init_margin_after - (other.init_margin_before or 0.0) for other in estimates[1:])
        equity_after = min(estimate.equity_with_loan_after for estimate in estimates)
        allowed = init_after <= config.max_margin_fraction * equity_after
        margins[action] = {"book": largest["book"], "init_margin_after": init_after,
                           "equity_with_loan_after": equity_after, "allowed": allowed}
        if not allowed:
            problems.append(f"{action} {largest['book']} would breach max_margin_fraction "
                            f"{config.max_margin_fraction:g}; lower the fraction or raise the limit")
    report["margin"] = margins
    if config.max_stop_risk_usd is not None and latest.entry and latest.entry.atr and latest.entry.stop_atr:
        risk = sum(largest[root] * MULTIPLIERS[root] for root in config.roots) * (
            latest.entry.atr * latest.entry.stop_atr)
        report["sizing"]["full_weight_stop_risk_usd"] = round(risk, 2)


def command_watch(config: ExecutorConfig, after: int | None) -> int:
    from .feed import SignalFeed

    stop = threading.Event()
    _stop_on_signals(stop)
    last = {"seq": after}

    def on_signal(target: Any) -> None:
        last["seq"] = max(last["seq"] or 0, target.seq)
        print(json.dumps({"signal": _describe(target)}), flush=True)

    def on_heartbeat(heartbeat: Any) -> None:
        print(json.dumps({"heartbeat": {"latest_seq": heartbeat.latest_seq,
                                        "sent_at": heartbeat.sent_at.isoformat()}}), flush=True)

    feed = SignalFeed(
        relay_url=config.relay_url, stream=config.stream, token=config.token(),
        verifier=_verifier(config), after=lambda: last["seq"], on_signal=on_signal,
        on_heartbeat=on_heartbeat, ca_file=str(config.ca_file) if config.ca_file else None,
    )
    feed.run(stop)
    return 0


def command_run(config: ExecutorConfig) -> int:
    from .executor import AckSender, Executor
    from .feed import SignalFeed
    from .ibkr import IBKRBroker

    journal = Journal(config.journal_path)
    token = config.token()
    notifications = None
    if config.discord_link_id:
        from .notifications import Notifications

        try:
            notifications = Notifications(config)
        except Exception as exc:  # noqa: BLE001 - optional notifications cannot disable trading
            LOGGER.error("Cannot initialize Discord notifications (%s)", type(exc).__name__)
    holder: dict[str, Any] = {}
    broker = IBKRBroker(config.ibkr, config.roots, on_update=lambda: holder["executor"].wake.set())
    executor = Executor(config, broker=broker, journal=journal, acks=AckSender(config, token),
                        notifications=notifications)
    holder["executor"] = executor
    feed = SignalFeed(
        relay_url=config.relay_url, stream=config.stream, token=token, verifier=_verifier(config),
        after=executor.resume_after, on_signal=executor.on_signal, on_heartbeat=executor.on_heartbeat,
        ca_file=str(config.ca_file) if config.ca_file else None,
    )
    stop = threading.Event()
    _stop_on_signals(stop, executor.wake)
    account = config.ibkr.account
    if config.sizing is not None:
        LOGGER.info("following %s as NQ + MNQ balance sizing at leverage fraction %g "
                    "(max %s per order) in %s account %s…%s", config.stream,
                    config.sizing.leverage_fraction, config.max_quantity, config.ibkr.account_type,
                    account[:2], account[-2:])
    else:
        LOGGER.info("following %s as %s x%s in %s account %s…%s", config.stream, config.root,
                    config.quantity, config.ibkr.account_type, account[:2], account[-2:])
    executor.run(stop, feed=feed)
    if notifications is not None:
        notifications.close()
    journal.close()
    return 0


def command_status(config: ExecutorConfig) -> int:
    journal = Journal(config.journal_path)
    latest = journal.latest_payload()
    target = None
    if latest is not None:
        try:
            target = _describe(parse_target(latest, config.stream))
        except SignalError:
            target = None
    print(json.dumps({
        "halt": journal.halt_reason(),
        "last_seq": journal.last_seq(),
        "target": target,
        "expected_positions": journal.expected_positions(),
        "book": _book(config, journal),
        "sizing": None if config.sizing is None else {
            "mode": config.sizing.mode, "leverage_fraction": config.sizing.leverage_fraction,
            "last_base": json.loads(journal.get_state("balance_base") or "null"),
            "account_value_health": json.loads(journal.get_state("sizing_health") or "null"),
        },
        "trades": journal.recent("trades", 5),
        "orders": journal.recent("orders", 10),
        "log": journal.recent("log", 10),
    }, indent=2, default=str))
    journal.close()
    return 0


def command_resume(config: ExecutorConfig) -> int:
    journal = Journal(config.journal_path)
    reason = journal.halt_reason()
    if reason is None:
        print("the executor is not halted")
        journal.close()
        return 0
    journal.set_state("resume_requested", datetime.now(UTC).isoformat())
    journal.log("resume_requested", {"halt": reason})
    journal.close()
    print(
        f"resume requested (halt was: {reason}). The running executor takes ownership of the "
        "broker's current position on its next step and aligns it with the latest target, "
        "which may close it."
    )
    return 0


def _stop_on_signals(stop: threading.Event, wake: threading.Event | None = None) -> None:
    def handler(_signum: int, _frame: Any) -> None:
        stop.set()
        if wake is not None:
            wake.set()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=str(default_config_path()))
    parser = argparse.ArgumentParser(prog="follow-executor")
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure", parents=[common], help="guided first-time setup")
    configure.add_argument("--advanced", action="store_true")
    settings = commands.add_parser(
        "settings", parents=[common],
        help="change sizing while flat; without options, ask for balance sizing or a fixed size")
    settings.add_argument("--root", choices=("MNQ", "NQ"))
    settings.add_argument("--quantity", type=int)
    settings.add_argument("--leverage-fraction", type=float,
                          help="balance sizing: fraction above 0, at most 1, of the leader's 6x band")
    check = commands.add_parser("check", parents=[common], help="verify relay, journal and IBKR")
    check.add_argument("--skip-broker", action="store_true")
    check.add_argument("--quotes", action="store_true", help="require a live quote; a closed market may leave this pending")
    commands.add_parser("maintenance-check", parents=[common], help="read-only flat-account and journal check")
    watch = commands.add_parser("watch", parents=[common], help="print verified signals only")
    watch.add_argument("--after", type=int)
    commands.add_parser("run", parents=[common], help="run the executor")
    commands.add_parser("status", parents=[common], help="show the journal")
    commands.add_parser("resume", parents=[common], help="clear a halt and adopt the position")
    discord = commands.add_parser("discord", parents=[common], help="link private Discord notifications")
    discord.add_argument("action", choices=("link", "enable", "status", "unlink"))
    gateway = commands.add_parser("gateway", parents=[common], help="manage IBC Gateway login automation")
    gateway.add_argument("action", choices=("configure", "start", "stop", "status", "logs", "run", "refresh", "container-stop"))
    gateway.add_argument("--backend", choices=("native", "docker"), help="Gateway installation backend (configure only)")
    gateway.add_argument("--vnc", action=argparse.BooleanOptionalAction, default=None,
                         help="enable/disable the private Docker recovery desktop (configure only)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # ibapi logs every wire message at INFO, including the account and login name.
    logging.getLogger("ibapi").setLevel(logging.WARNING)
    os.umask(0o077)
    try:
        path = Path(args.config).expanduser().resolve()
        if args.command == "gateway":
            from .gateway import dispatch

            return dispatch(path, args.action, backend=args.backend, vnc=args.vnc)
        with ExitStack() as locks:
            if args.command not in ("status", "resume"):
                locks.enter_context(exclusive(path.with_suffix(path.suffix + ".lock")))
            if args.command == "configure":
                from .setup import initial_config

                return initial_config(path, advanced=args.advanced)
            if args.command == "settings":
                from .setup import change_settings, initial_config

                if args.root is None and args.quantity is None and args.leverage_fraction is None:
                    if not path.exists():
                        raise ConfigError("run configure first")
                    return initial_config(path)
                if args.leverage_fraction is not None:
                    if args.root is not None or args.quantity is not None:
                        parser.error("--leverage-fraction cannot be combined with --root or --quantity")
                    if not 0 < args.leverage_fraction <= 1:
                        parser.error("--leverage-fraction must be above 0 and at most 1")
                return change_settings(path, root=args.root, quantity=args.quantity,
                                       fraction=args.leverage_fraction)
            config = load_config(path)
            if args.command == "discord":
                from .notifications import configure as configure_discord

                return configure_discord(path, config, args.action)
            if args.command in ("run", "watch", "check", "maintenance-check"):
                journal_lock = config.journal_path.with_suffix(config.journal_path.suffix + ".lock")
                if journal_lock != path.with_suffix(path.suffix + ".lock"):
                    locks.enter_context(exclusive(journal_lock))
            if args.command == "check":
                if args.skip_broker and args.quotes:
                    raise ConfigError("--quotes requires the broker check")
                return command_check(config, skip_broker=args.skip_broker, quotes=args.quotes)
            if args.command == "maintenance-check":
                from .maintenance_probe import check

                print(json.dumps(check(config), sort_keys=True))
                return 0
            if args.command == "watch":
                return command_watch(config, args.after)
            if args.command == "run":
                journal = Journal(config.journal_path)
                try:
                    bind_settings(journal, config)
                finally:
                    journal.close()
                return command_run(config)
            if args.command == "status":
                return command_status(config)
            return command_resume(config)
    except (ConfigError, OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"follow-executor: {exc}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
