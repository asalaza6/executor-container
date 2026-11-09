# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""The executor service: feed, journal, decisions and the broker in one loop."""

from __future__ import annotations

import json
import logging
import math
import queue
import ssl
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from .broker import (
    BOOK_ROOTS,
    MULTIPLIERS,
    Broker,
    BrokerState,
    FutureContract,
    MarginEstimate,
    OrderRequest,
    OrderView,
)
from .config import ExecutorConfig
from .engine import (
    Action,
    Cancel,
    Halt,
    MarkTrade,
    Modify,
    Place,
    View,
    decide_book,
    desired_stop,
    exit_request,
    stop_request,
)
from .journal import Journal
from .protection import ProtectionWatch
from .signal import Heartbeat, SignalError, Target, parse_target
from .sizing import balance_base, book_label, leg_units, split

LOGGER = logging.getLogger(__name__)
ACK_TIMEOUT = timedelta(seconds=5)
CANCEL_RETRY = timedelta(seconds=3)
MISMATCH_GRACE = timedelta(seconds=5)
REFRESH_INTERVAL = timedelta(seconds=30)
RECONNECT_INTERVAL = timedelta(seconds=10)
STATE_ACK_INTERVAL = timedelta(seconds=60)
NET_LIQUIDATION_MAX_AGE = timedelta(seconds=60)
BALANCE_TRADES_KEPT = 100


def utc_now() -> datetime:
    return datetime.now(UTC)


def public_ack(kind: str, detail: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Keep local account, position and margin details out of relay telemetry."""
    if kind in ("missed", "refused", "error"):
        reason = str(detail.get("reason", ""))
        code = "local_check_failed"
        for prefix, name in (
            ("entry deadline", "entry_deadline_passed"),
            ("signal carries no leader sizing", "sizing_missing"),
            ("balance sizing", "sizing_unavailable"),
            ("balance base is 0", "balance_too_small"),
            ("size rounds to 0", "size_rounds_to_zero"),
            ("order quantity", "quantity_limit"),
            ("stop risk", "stop_risk_limit"),
            ("initial margin", "margin_limit"),
            ("margin check unavailable", "margin_unavailable"),
            ("account ", "account_mismatch"),
            ("broker position", "position_mismatch"),
            ("positions in more", "multiple_contracts"),
            ("exit order", "exit_rejected"),
            ("order ", "order_check_failed"),
        ):
            if reason.startswith(prefix):
                code = name
                break
        if kind == "error":
            return kind, {"halted": True, "reason": code}
        # The public relay accepts 'rejected', not internal trade-status names.
        return "rejected", {"outcome": kind, "reason": code}
    if kind == "received":
        return kind, {"cause": detail.get("cause")}
    if kind == "state":
        return kind, {key: detail.get(key) for key in (
            "position", "matches_target", "halted", "heartbeat_age_seconds"
        )}
    safe = {}
    if detail.get("purpose") in ("entry", "stop", "exit"):
        safe["purpose"] = detail["purpose"]
    if type(detail.get("code")) is int:
        safe["code"] = detail["code"]
    return kind, safe


class AckSender:
    """Best-effort acknowledgements to the relay; never blocks the executor."""

    def __init__(self, config: ExecutorConfig, token: str) -> None:
        self._url = f"{config.relay_url}/v1/acks"
        self._stream = config.stream
        self._token = token
        self._enabled = config.send_acks
        self._context = (
            ssl.create_default_context(cafile=str(config.ca_file) if config.ca_file else None)
            if config.relay_url.startswith("https")
            else None
        )
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1000)
        self._failing = False

    def send(self, kind: str, seq: int | None, detail: dict[str, Any]) -> None:
        if not self._enabled:
            return
        kind, detail = public_ack(kind, detail)
        try:
            self._queue.put_nowait({"stream": self._stream, "seq": seq, "kind": kind, "detail": detail})
        except queue.Full:
            pass

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                body = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            request = urllib.request.Request(
                self._url,
                data=json.dumps(body, separators=(",", ":")).encode(),
                method="POST",
                headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=5, context=self._context) as response:
                    response.read()
                self._failing = False
            except Exception as exc:  # noqa: BLE001 - acknowledgements are best effort
                if not self._failing:
                    LOGGER.warning("acknowledgements failing: %s", exc)
                self._failing = True


class NullAcks:
    def send(self, kind: str, seq: int | None, detail: dict[str, Any]) -> None:
        pass


@dataclass
class Pending:
    kind: str  # place, modify or cancel
    since: datetime
    purpose: str | None = None
    stop_price: float | None = None
    quantity: int | None = None


def _acknowledged(pending: Pending, order: OrderView | None, filled: bool) -> bool:
    if pending.kind == "place":
        return order is not None or filled
    if order is None or not order.working:
        return True
    if pending.kind == "modify":
        return order.stop_price == pending.stop_price and order.remaining == pending.quantity
    return False


class Executor:
    def __init__(
        self,
        config: ExecutorConfig,
        *,
        broker: Broker,
        journal: Journal,
        acks: AckSender | NullAcks | None = None,
        clock: Callable[[], datetime] = utc_now,
        notifications: Any = None,
    ) -> None:
        self.config = config
        self.broker = broker
        self.journal = journal
        self.acks = acks or NullAcks()
        self.clock = clock
        self.notifications = notifications
        self.wake = threading.Event()
        self.feed_behind = False
        self.pending: dict[int, Pending] = {}
        self.target = self._load_target()
        self.last_heartbeat_at: datetime | None = None
        self._lock = threading.Lock()
        self._contracts: dict[tuple[str, str], FutureContract] = {}
        self._margin: dict[tuple[int, str, int], tuple[datetime, MarginEstimate]] = {}
        self._net_liquidation_cache: tuple[datetime, float] | None = None
        self._net_liquidation_warmed = datetime.min.replace(tzinfo=UTC)
        self._mismatch_since: datetime | None = None
        self._rejection_seq = int(journal.get_state("rejection_seq") or 0)
        self._next_connect = datetime.min.replace(tzinfo=UTC)
        self._next_refresh = datetime.min.replace(tzinfo=UTC)
        self._next_state_ack = datetime.min.replace(tzinfo=UTC)
        self._warned: set[str] = set()
        self._feed_stale = False
        self._broker_down_since: datetime | None = None
        self._started_at = self.clock()
        self._heartbeat_seq = 0
        self._service_started = False
        self._protection = ProtectionWatch(journal)
        self._protection_refresh: dict[int, int] = {}
        self._orphan_stops: dict[str, dict] = json.loads(journal.get_state("orphan_stops") or "{}")
        self._orphan_refresh: int | None = None
        self._orphan_refresh_at = datetime.min.replace(tzinfo=UTC)

    # Feed callbacks (feed thread) -----------------------------------------

    def on_signal(self, target: Target) -> None:
        with self._lock:
            new = self.journal.record_signal(target.seq, target.payload)
            if self.target is None or target.seq > self.target.seq:
                self.target = target
        if new:
            LOGGER.info("signal %s %s %s stop=%s", target.seq, target.cause, target.position, target.stop)
            self.acks.send("received", target.seq, {"cause": target.cause})
        self.wake.set()

    def on_heartbeat(self, heartbeat: Heartbeat) -> None:
        self.last_heartbeat_at = self.clock()
        self._heartbeat_seq = heartbeat.latest_seq
        if heartbeat.latest_seq > self.journal.last_seq():
            self.feed_behind = True
            self.wake.set()

    def resume_after(self) -> int | None:
        return self.journal.last_seq() or None

    # The loop ---------------------------------------------------------------

    def run(self, stop: threading.Event, *, feed: Any = None, acks_thread: bool = True) -> None:
        threads = []
        notification_stop = threading.Event()
        self._service_started = True
        if feed is not None:
            threads.append(threading.Thread(target=feed.run, args=(stop,), name="feed", daemon=True))
        if acks_thread and isinstance(self.acks, AckSender):
            threads.append(threading.Thread(target=self.acks.run, args=(stop,), name="acks", daemon=True))
        if self.notifications is not None:
            self.notifications.status("executor", "starting", self.clock(), force=True)
            threads.append(threading.Thread(target=self.notifications.run, args=(notification_stop,),
                                            name="notifications", daemon=True))
        for thread in threads:
            thread.start()
        try:
            while not stop.is_set():
                try:
                    self.step()
                except Exception:
                    LOGGER.exception("executor step failed")
                if self.feed_behind and feed is not None:
                    self.feed_behind = False
                    feed.reconnect()
                self.wake.wait(0.25)
                self.wake.clear()
        finally:
            stop.set()
            if self.notifications is not None:
                self.notifications.status("executor", "stopped", self.clock())
                notification_stop.set()
            if feed is not None:
                feed.reconnect()
            self.broker.disconnect()
            for thread in threads:
                thread.join(timeout=12 if thread.name == "notifications" else 6)

    def step(self) -> list[Action]:
        try:
            actions = self._step()
        except Exception:
            if self.notifications is not None:
                self.notifications.status("execution_loop", "failed", self.clock())
            raise
        else:
            if self.notifications is not None:
                self.notifications.status("execution_loop", "ready", self.clock(), announce_initial=False, debounce=5)
            return actions
        finally:
            self._observe_health()

    def _step(self) -> list[Action]:
        now = self.clock()
        self._watch_feed(now)
        if not self._ensure_connected(now):
            return []
        if now >= self._next_refresh:
            self.broker.refresh()
            self._next_refresh = now + REFRESH_INTERVAL
        state = self.broker.state()
        self._absorb(state, now)
        if self.notifications is not None:
            self.notifications.observe(state, self.journal, now,
                                       self.target.cause if self.target else None)

        halt = self.journal.halt_reason()
        if self.journal.get_state("resume_requested") is not None:
            if halt is not None:
                self.journal.set_baseline(state.positions)
                # Resume explicitly adopts the current broker positions. An
                # orphan-fill offset belongs to the previous journal baseline.
                for record in self._protection.records.values():
                    record["position_offset"] = 0
                if self._protection.records:
                    self._protection.save()
                for record in self._orphan_stops.values():
                    record["phase"] = "checking"
                    record["verify_after"] = (now + MISMATCH_GRACE).isoformat()
                if self._orphan_stops:
                    self._save_orphans()
                    self._orphan_refresh = None
                self._mismatch_since = None
                LOGGER.warning("resumed; the executor now owns positions %s", state.positions)
                halt = None
            self.journal.clear_halt()
        if halt is None:
            problem = self._integrity(state, now)
            if problem is not None:
                self._halt(problem)
                halt = problem

        self._protection.observe(state, now, self.target)
        safety_actions = self._orphan_stop_actions(state, now)
        if safety_actions is None:
            safety_actions = self._protection_actions(state, now)
        if safety_actions is not None:
            for action in safety_actions:
                self._execute(action, now)
            return safety_actions

        if self._waiting(now):
            return []
        if halt is None and self._mismatch_since is not None:
            # An unexplained position is never traded: either our own fill report
            # catches up within the grace, or the executor halts.
            return []
        sized: list[Action] = []
        if halt is None and self.config.sizing is not None:
            refusal = self._size_entry(state, now)
            if refusal is not None:
                self._execute(refusal, now)
                sized.append(refusal)
        views = self._views(state, now)
        if halt is not None:
            actions = [action for view in views for action in self._protect(view)]
        else:
            actions = self._screen_entries(decide_book(views), now)
        for action in actions:
            self._execute(action, now)
        if halt is None and not actions:
            self._warm_margin(views, now)
        self._state_ack(views, now, halt)
        return sized + actions

    def _observe_health(self) -> None:
        if self.notifications is None:
            return
        try:
            self.notifications.pulse()
            now = self.clock()
            if self._service_started:
                self.notifications.status("executor", "halted" if self.journal.halt_reason() else "running", now)
            if not hasattr(self.broker, "health"):
                return
            state = self.broker.state()
            contracts = {con_id: state.contracts[con_id] for con_id, quantity in state.positions.items()
                         if quantity and con_id in state.contracts}
            target = self.target
            for root in self.config.roots:
                current = self._contracts.get((root, target.contract_month)) if target is not None else None
                if current is not None:
                    contracts[current.con_id] = current
            self.broker.monitor_market_data(list(contracts.values()))
            health = self.broker.health()
            market = health["market_data"]
            if not health["connected"]:
                status = "api_unavailable"
            elif not health["reconciled"]:
                status = "reconciling"
            elif self.journal.halt_reason():
                status = "reconciliation_required"
            elif self._mismatch_since is not None:
                status = "reconciling"  # Allow the normal fill/position callback grace period.
            elif market == "idle":
                # A known target with unresolved details is not a verified subscription.
                status = "market_data_waiting" if target and target.contract_month else "api_ready"
            elif market == "pending":
                status = "market_data_waiting"
            else:
                status = "ready" if market == "ready" else "market_data_" + market
            debounce = 30 if status in {"reconciling", "market_data_waiting"} else 5
            if status in {"api_unavailable", "reconciliation_required"}:
                debounce = 0
            self.notifications.status("gateway", status, now, debounce=debounce)
        except Exception as exc:  # noqa: BLE001 - health probes never gate trading
            self._warn_once("notification_health", f"Service health observation failed ({type(exc).__name__})")

    # Connection, absorption and integrity ----------------------------------

    def _ensure_connected(self, now: datetime) -> bool:
        if self.broker.is_connected:
            return True
        if now < self._next_connect:
            return False
        self._next_connect = now + RECONNECT_INTERVAL
        try:
            self.broker.connect()
            accounts = self.broker.managed_accounts
            if self.config.ibkr.account not in accounts:
                self.broker.disconnect()
                self._halt(f"account {self.config.ibkr.account} is not managed by this login")
                return False
            self.broker.refresh()
            self.broker.wait_for_snapshot()
            self._next_refresh = now + REFRESH_INTERVAL
            self._mismatch_since = None
            if self._broker_down_since is None:
                LOGGER.info("connected to IBKR")
            else:
                LOGGER.info("IBKR connection restored after %.0f s",
                            (now - self._broker_down_since).total_seconds())
                self._broker_down_since = None
            return True
        except Exception as exc:  # noqa: BLE001 - retry later
            self.broker.disconnect()
            if self._broker_down_since is None:
                self._broker_down_since = now
                LOGGER.warning("IBKR unavailable (%s); retrying every %.0f s until it returns",
                               exc, RECONNECT_INTERVAL.total_seconds())
            return False

    def _absorb(self, state: BrokerState, now: datetime) -> None:
        purposes = {oid: order.purpose for oid, order in state.orders.items() if order.purpose}
        filled = False
        for execution in state.executions:
            if not execution.order_ref.startswith("fx:"):
                continue
            if self.journal.record_execution(execution):
                filled = True
                purpose = execution.order_ref.split(":")[1] if ":" in execution.order_ref else None
                contract = state.contracts.get(execution.con_id)
                LOGGER.info("fill: %s %s %s %s @ %s", purpose, execution.side, execution.quantity,
                            contract.root if contract else "", execution.price)
                self.acks.send("filled", self._seq(), {"purpose": purpose})
        if filled and self.config.sizing is not None:
            LOGGER.info("position: %s", self.book(state))
        for order_id, order in state.orders.items():
            if order.purpose and order.client_id == self.config.ibkr.client_id:
                self.journal.set_order_status(order_id, order.status)

        for rejection in state.rejections:
            if rejection.seq <= self._rejection_seq:
                continue
            self._rejection_seq = rejection.seq
            self.journal.set_state("rejection_seq", str(rejection.seq))
            pending = self.pending.get(rejection.order_id)
            purpose = purposes.get(rejection.order_id) or (pending.purpose if pending else None)
            if rejection.cancel_refused:
                self._protection.cancel_refused(rejection.order_id)
                if pending is not None and pending.kind == "cancel":
                    self.pending.pop(rejection.order_id, None)
                continue
            if pending is None and purpose is None:
                continue
            self.pending.pop(rejection.order_id, None)
            self.journal.set_order_status(rejection.order_id, "Rejected")
            self.journal.log("rejected", {"order_id": rejection.order_id, "purpose": purpose,
                                          "code": rejection.code, "message": rejection.message})
            LOGGER.error("broker rejected %s order %s: %s %s", purpose, rejection.order_id,
                         rejection.code, rejection.message)
            self.acks.send("rejected", self._seq(), {"purpose": purpose, "code": rejection.code})
            key = self._trade_of(rejection.order_id) or (
                self.target.trade_key if self.target is not None else None
            )
            if purpose == "entry" and key is not None:
                self.journal.mark_trade(key, "rejected", f"broker: {rejection.message}")
            elif purpose == "stop" and key is not None:
                self.journal.mark_trade(key, "closing", f"stop refused: {rejection.message}")
            elif purpose == "exit":
                self._halt(f"exit order {rejection.order_id} rejected: {rejection.message}")

        for order_id, pending in list(self.pending.items()):
            filled = any(item.order_id == order_id for item in state.executions)
            if _acknowledged(pending, state.orders.get(order_id), filled):
                self.pending.pop(order_id)

    def _integrity(self, state: BrokerState, now: datetime) -> str | None:
        label = "/".join(self.config.roots)
        for order in state.orders.values():
            if order.working and (order.purpose is None or order.client_id != self.config.ibkr.client_id):
                return f"order {order.order_id} on {label} was not placed by this executor"
        held = {con_id: qty for con_id, qty in state.positions.items() if qty}
        if len(held) > 1 and not self._one_book(state, held):
            return f"positions in more than one {label} contract: {held}"
        expected = self.journal.expected_positions()
        if held == expected:
            self._mismatch_since = None
            return None
        if self._mismatch_since is None:
            self._mismatch_since = now
        elif now - self._mismatch_since > MISMATCH_GRACE:
            return f"broker position {held} differs from the executor's record {expected}"
        return None

    def _one_book(self, state: BrokerState, held: dict[int, int]) -> bool:
        """Balance sizing holds exactly one NQ and one MNQ position of one month."""
        if self.config.sizing is None or len(held) != 2:
            return False
        contracts = [state.contracts.get(con_id) for con_id in held]
        return (all(contracts) and sorted(c.root for c in contracts) == sorted(BOOK_ROOTS)
                and len({c.contract_month for c in contracts}) == 1)

    def _waiting(self, now: datetime) -> bool:
        for order_id, pending in list(self.pending.items()):
            if now - pending.since <= ACK_TIMEOUT:
                return True
            if pending.kind == "cancel":
                self.pending.pop(order_id)
                continue
            self._halt(f"{pending.kind} of order {order_id} was not acknowledged within 5 s")
            self.pending.pop(order_id)
            return True
        return False

    def _save_orphans(self) -> None:
        self.journal.set_state("orphan_stops", json.dumps(self._orphan_stops, sort_keys=True))

    def _orphan_stop_actions(self, state: BrokerState, now: datetime) -> list[Action] | None:
        """Cancel our stops on confirmed-flat contracts, even during a halt.

        A fresh snapshot prevents a delayed position callback from being mistaken
        for flat. Persist cleanup before cancellation and block new entries until
        another snapshot resolves cancellation/fill races.
        """
        expected = self.journal.expected_positions()
        for order in state.orders.values():
            if (order.working and order.purpose == "stop"
                    and order.client_id == self.config.ibkr.client_id
                    and not state.positions.get(order.con_id)
                    and str(order.order_id) not in self._orphan_stops):
                self._orphan_stops[str(order.order_id)] = {
                    "con_id": order.con_id, "phase": "checking",
                    "trade_key": self._trade_of(order.order_id),
                    "verify_after": (now + (MISMATCH_GRACE if expected.get(order.con_id)
                                            else timedelta())).isoformat(),
                }
                self._orphan_refresh = None
                self._save_orphans()
        if not self._orphan_stops:
            self._orphan_refresh = None
            return None
        if self._orphan_refresh is None:
            self._orphan_refresh = state.snapshot_id
            self._orphan_refresh_at = now
            self.broker.refresh()
            return []
        if not state.snapshot_complete:
            return []
        if state.snapshot_id <= self._orphan_refresh:
            self._orphan_refresh_at = now
            self.broker.refresh()
            return []

        actions: dict[int, Cancel] = {}
        for key, record in list(self._orphan_stops.items()):
            con_id = record["con_id"]
            order = state.orders.get(int(key))
            position = state.positions.get(con_id, 0)
            if record["phase"] == "checking":
                if position or order is None or not order.working:
                    del self._orphan_stops[key]
                    continue
                if expected.get(con_id):
                    verify_after = datetime.fromisoformat(record["verify_after"])
                    if now < verify_after:
                        continue
                    if self._orphan_refresh_at < verify_after:
                        self._orphan_refresh = None
                        continue
                record["phase"] = "cancelling"
                record["expected_before"] = expected.get(con_id, 0)
                self.journal.log("orphan_stop", {"order_id": int(key), "con_id": con_id})
                LOGGER.warning("cancelling orphan stop %s on a flat contract", key)
            elif position or expected.get(con_id, 0) != record["expected_before"]:
                # A stop/entry filled after verified flat while cancellation was
                # in flight. Reconcile and close only the executor-owned exposure.
                self._protection.force_close(con_id, now, "fill during orphan stop cancellation",
                                             record["trade_key"], position_offset=record["expected_before"])
                del self._orphan_stops[key]
                continue
            working = [item for item in state.orders.values()
                       if item.con_id == con_id and item.working
                       and item.client_id == self.config.ibkr.client_id
                       and item.purpose in {"stop", "entry"}]
            if not working:
                del self._orphan_stops[key]
                continue
            for item in working:
                pending = self.pending.get(item.order_id)
                if pending is None or pending.kind != "cancel" or now - pending.since >= CANCEL_RETRY:
                    actions[item.order_id] = Cancel(item.order_id, "stop on a flat contract")
        # Save the cancelling phase before calling the broker, including across a
        # process death between submitting cancel and receiving its callback.
        self._save_orphans()
        if actions:
            self._orphan_refresh = None
            return list(actions.values())
        return [] if self._orphan_stops else None

    def _protection_actions(self, state: BrokerState, now: datetime) -> list[Action] | None:
        """Close timed-out exposure even while normal decisions/acks are halted.

        Every cancellation/submission is followed by a fresh broker snapshot.
        Never race a stop or a remaining entry, or guess an unreconciled quantity.
        """
        closing = [int(key) for key, record in self._protection.records.items() if record["closing"]]
        if not closing:
            return None
        con_id = closing[0]
        record = self._protection.records[str(con_id)]
        reason = record["reason"]
        target = self.target
        contract = state.contracts.get(con_id)
        if (target is not None and contract is not None
                and target.contract_month == contract.contract_month and target.trade_key
                and target.trade_key not in record["trade_keys"]):
            record["trade_keys"].append(target.trade_key)
            self._protection.save()
        for key in record["trade_keys"]:
            if self.journal.trade_status(key) not in {"closing", "closed"}:
                self._execute(MarkTrade(key, "closing", reason), now)
                LOGGER.error("%s; closing the unprotected position", reason)

        # A complete snapshot requested after the last action also covers fills
        # that raced cancellation or were missed across a disconnect/restart.
        if con_id not in self._protection_refresh:
            self._protection_refresh[con_id] = state.snapshot_id
            self.broker.refresh()
            return []
        if not state.snapshot_complete:
            return []
        if state.snapshot_id <= self._protection_refresh[con_id]:
            # refresh() can defer while an earlier periodic snapshot is in flight.
            # Once that finishes, request the safety snapshot without waiting 30 s.
            self.broker.refresh()
            return []
        position = state.positions.get(con_id, 0)
        expected = self.journal.expected_positions().get(con_id, 0) - record.get("position_offset", 0)
        if position != expected:
            return []
        orders = [order for order in state.orders.values() if order.con_id == con_id]
        filled = {}
        for execution in self.journal.notification_executions():
            oid = execution["order_id"]
            filled[oid] = filled.get(oid, 0) + execution["quantity"]
        if any(order.client_id == self.config.ibkr.client_id and order.purpose
               and order.filled > filled.get(order.order_id, 0) for order in orders):
            return []  # Wait for executions before deciding how much is left.
        working = [order for order in state.orders.values() if order.working]
        if any(order.client_id != self.config.ibkr.client_id or not order.purpose for order in working):
            self._halt("protection exit blocked by an order from another client")
            return []

        # Unknown submission outcomes must be settled by a subsequent snapshot,
        # never by blindly sending a second market exit after an ack timeout.
        for oid, order in self.journal.notification_orders().items():
            if order["con_id"] != con_id or oid in state.orders:
                continue
            pending = self.pending.get(oid)
            if pending is not None and now - pending.since <= ACK_TIMEOUT:
                self._protection_refresh.pop(con_id, None)
                return []
            if order["status"] in {"submitted", "ApiPending", "PendingSubmit", "PreSubmitted",
                                   "Submitted", "PendingCancel"}:
                self.journal.set_order_status(oid, "Absent")
                self.pending.pop(oid, None)

        exits = [order for order in working if position and order.con_id == con_id and order.purpose == "exit"
                 and order.action == ("SELL" if position > 0 else "BUY")
                 and order.order_type == "MKT" and order.remaining == abs(position)]
        keep_exit = exits[0].order_id if len(exits) == 1 else None
        cancel = [order for order in working if order.order_id != keep_exit]
        if self.config.sizing is not None:
            # The book's other contract keeps its own stop or exit while it holds.
            cancel = [order for order in cancel if order.con_id == con_id or order.purpose == "entry"
                      or not state.positions.get(order.con_id)]
        if cancel:
            actions: list[Action] = []
            for order in cancel:
                pending = self.pending.get(order.order_id)
                if pending is None or pending.kind != "cancel" or now - pending.since >= CANCEL_RETRY:
                    actions.append(Cancel(order.order_id, reason))
            if actions:
                self._protection_refresh.pop(con_id, None)
            return actions
        if keep_exit is not None:
            return []
        if not position:
            for key in record["trade_keys"]:
                self._execute(MarkTrade(key, "closed", reason), now)
            self._protection.finish(con_id)
            self._protection_refresh.pop(con_id, None)
            return []
        if contract is None:
            self._halt("protection exit cannot resolve the held contract")
            return []
        retry_at = record.get("retry_at")
        if retry_at and now < datetime.fromisoformat(retry_at):
            return []
        record["retry_at"] = (now + CANCEL_RETRY).isoformat()
        self._protection.save()
        self._protection_refresh.pop(con_id, None)
        key = record["trade_keys"][-1] if record["trade_keys"] else None
        return [Place(exit_request(position, contract, target), key)]

    def _view(self, state: BrokerState, now: datetime) -> View:
        target = self.target
        held = {con_id: qty for con_id, qty in state.positions.items() if qty}
        con_id, position = next(iter(held.items()), (None, 0))
        position_contract = None if con_id is None else state.contracts.get(con_id)
        target_contract = None
        if target is not None and target.direction and target.contract_month:
            target_contract = self._contract(self.config.root, target.contract_month)
        ours = [
            order
            for order in state.orders.values()
            if order.working and order.purpose and order.client_id == self.config.ibkr.client_id
        ]
        key = target.trade_key if target is not None else None
        entry_price = self.journal.entry_price(key) if key else None
        if entry_price is None and con_id is not None:
            entry_price = state.average_prices.get(con_id)
        return View(
            now=now,
            target=target,
            quantity=self.config.quantity,
            slippage_points=self.config.max_entry_slippage_points,
            clock_exit_grace=timedelta(seconds=self.config.clock_exit_grace_seconds),
            position=position,
            position_contract=position_contract,
            target_contract=target_contract,
            stops=tuple(o for o in ours if o.purpose == "stop"),
            entries=tuple(o for o in ours if o.purpose == "entry"),
            exits=tuple(o for o in ours if o.purpose == "exit"),
            order_trades=self.journal.order_trades(),
            trade_status=self.journal.trade_status(key),
            entry_price=entry_price,
        )

    def _views(self, state: BrokerState, now: datetime) -> list[View]:
        """One view per traded contract: the fixed root, or the NQ and MNQ book."""
        if self.config.sizing is None:
            return [self._view(state, now)]
        target = self.target
        key = target.trade_key if target is not None else None
        roots = self._roots(state)
        held = {con_id: qty for con_id, qty in state.positions.items() if qty}
        ours = [
            order
            for order in state.orders.values()
            if order.working and order.purpose and order.client_id == self.config.ibkr.client_id
        ]
        sizes = self._book_sizes(key, held, roots)
        order_trades = self.journal.order_trades()
        trade_status = self.journal.trade_status(key)
        views = []
        for root in self.config.roots:
            con_id, position = next(((c, q) for c, q in held.items() if roots.get(c) == root), (None, 0))
            target_contract = None
            # Only a contract this trade sizes is needed; a 7 MNQ book never resolves NQ.
            if target is not None and target.direction and target.contract_month and sizes.get(root):
                target_contract = self._contract(root, target.contract_month)
            entry_price = self._entry_price(key, con_id) if key and con_id is not None else None
            if entry_price is None and con_id is not None:
                entry_price = state.average_prices.get(con_id)
            mine = [order for order in ours if (roots.get(order.con_id) or order.root) == root]
            views.append(View(
                now=now,
                target=target,
                quantity=sizes.get(root, 0),
                slippage_points=self.config.max_entry_slippage_points,
                clock_exit_grace=timedelta(seconds=self.config.clock_exit_grace_seconds),
                position=position,
                position_contract=None if con_id is None else state.contracts.get(con_id),
                target_contract=target_contract,
                stops=tuple(o for o in mine if o.purpose == "stop"),
                entries=tuple(o for o in mine if o.purpose == "entry"),
                exits=tuple(o for o in mine if o.purpose == "exit"),
                order_trades=order_trades,
                trade_status=trade_status,
                entry_price=entry_price,
            ))
        return views

    def _protect(self, view: View) -> list[Action]:
        """While halted: only repair a missing stop on a held position."""

        if not view.position or view.stops or view.target is None or view.position_contract is None:
            return []
        if view.target.direction != (1 if view.position > 0 else -1):
            return []
        price = desired_stop(view, view.target, view.target.direction)
        if price is None:
            return []
        request = stop_request(view.position, price, view.position_contract, view.target)
        return [Place(request, view.target.trade_key)]

    # Balance sizing -----------------------------------------------------------

    def _roots(self, state: BrokerState) -> dict[int, str]:
        roots = {int(con_id): root for con_id, root in
                 json.loads(self.journal.get_state("contract_roots") or "{}").items()}
        roots.update({con_id: contract.root for con_id, contract in state.contracts.items()})
        return roots

    def _remember_root(self, contract: FutureContract) -> None:
        roots = json.loads(self.journal.get_state("contract_roots") or "{}")
        if roots.get(str(contract.con_id)) != contract.root:
            roots[str(contract.con_id)] = contract.root
            self.journal.set_state("contract_roots", json.dumps(roots, sort_keys=True))

    def book(self, state: BrokerState) -> str:
        """The journal's expected position by root, such as ``1 NQ + 5 MNQ``."""
        roots = self._roots(state)
        quantities: dict[str, int] = {}
        for con_id, quantity in self.journal.expected_positions().items():
            root = roots.get(con_id, "?")
            quantities[root] = quantities.get(root, 0) + quantity
        return book_label(quantities)

    def _balance_trades(self) -> dict[str, dict[str, Any]]:
        return json.loads(self.journal.get_state("balance_trades") or "{}")

    def _book_sizes(self, key: str | None, held: dict[int, int], roots: dict[int, str]) -> dict[str, int]:
        record = self._balance_trades().get(key) if key else None
        if record is not None:
            return {root: int(record[root]) for root in BOOK_ROOTS}
        # A held book under a new trade key, such as gap_drift_continuation,
        # never resizes: each contract keeps the quantity it holds.
        sizes: dict[str, int] = {}
        for con_id, quantity in held.items():
            if con_id in roots:
                sizes[roots[con_id]] = sizes.get(roots[con_id], 0) + abs(quantity)
        return sizes

    def _entry_price(self, key: str, con_id: int) -> float | None:
        orders = self.journal.notification_orders()
        fills = [(item["quantity"], item["price"]) for item in self.journal.notification_executions()
                 if item["con_id"] == con_id and orders.get(item["order_id"], {}).get("trade_key") == key
                 and orders[item["order_id"]]["purpose"] == "entry"]
        total = sum(quantity for quantity, _ in fills)
        return sum(quantity * price for quantity, price in fills) / total if total else None

    def _net_liquidation(self, now: datetime) -> float | None:
        cached = self._net_liquidation_cache
        if cached is not None and now - cached[0] <= NET_LIQUIDATION_MAX_AGE:
            return cached[1]
        try:
            value = float(self.broker.net_liquidation())
        except Exception as exc:  # noqa: BLE001 - sizing reuses the last base instead
            self._warn_once("net_liquidation", f"NetLiquidation unavailable: {exc}")
            self._record_sizing_health("unavailable", now)
            return None
        if not math.isfinite(value) or value <= 0:
            self._record_sizing_health("unavailable", now)
            return None
        self._record_sizing_health("ready", now)
        self._net_liquidation_cache = (now, value)
        return value

    def _record_sizing_health(self, status: str, now: datetime) -> None:
        previous = json.loads(self.journal.get_state("sizing_health") or "null")
        current = {"status": status, "checked_at": now.isoformat()}
        self.journal.set_state("sizing_health", json.dumps(current))
        if previous is None or previous["status"] != status:
            self.journal.log("sizing_health", current)
            LOGGER.info("Balance sizing account-value health: %s", status)

    def _size_entry(self, state: BrokerState, now: datetime) -> MarkTrade | None:
        """Size a new flat entry once, before its orders, and persist the result."""
        target = self.target
        if target is None or not target.direction or target.entry is None or now > target.entry.deadline:
            return None
        key = target.trade_key
        assert key is not None
        if self.journal.trade_status(key) is not None or key in self._balance_trades():
            return None
        if (any(state.positions.values()) or self.journal.expected_positions()
                or any(order.working and order.purpose == "entry" for order in state.orders.values())):
            return None
        quantities, detail = self._balance_quantities(target, now)
        if quantities is None:
            LOGGER.warning("balance entry %s refused: %s", key, detail)
            return MarkTrade(key, "refused", detail)
        trades = self._balance_trades()
        trades[key] = detail
        for old in list(trades)[:-BALANCE_TRADES_KEPT]:
            del trades[old]
        self.journal.set_state("balance_trades", json.dumps(trades))
        self.journal.log("balance_size", {"trade": key, **detail})
        LOGGER.info("balance size for %s: %s (base %s, weight %s)", key, book_label(quantities),
                    detail["base"], detail["weight"])
        return None

    def _balance_quantities(self, target: Target, now: datetime) -> tuple[dict[str, int] | None, Any]:
        assert self.config.sizing is not None and target.entry is not None
        band = target.sizing
        if band is None:
            return None, "signal carries no leader sizing; balance entries need its leg weight and band"
        fraction = self.config.sizing.leverage_fraction
        last = json.loads(self.journal.get_state("balance_base") or "null")
        previous = None if last is None else int(last["base"])
        equity = self._net_liquidation(now)
        price = target.entry.reference_price
        if equity is None or price is None:
            missing = "NetLiquidation" if equity is None else "reference price"
            if previous is None:
                return None, f"balance sizing unavailable: no {missing} and no earlier balance base"
            LOGGER.warning("%s unavailable; reusing the last balance base %s", missing, previous)
            base = previous
        else:
            base = balance_base(previous, equity, price, fraction, band)
            if base < 1:
                return None, (f"balance base is 0 at NetLiquidation {equity:,.0f} and NQ {price:,.2f} "
                              f"with leverage fraction {fraction:g}")
            self.journal.set_state("balance_base", json.dumps({
                "base": base, "trade_key": target.trade_key, "at": now.isoformat(),
                "net_liquidation": equity, "reference_price": price, "leverage_fraction": fraction,
            }))
        units = leg_units(base, band.weight)
        if units < 1:
            # No minimum size: a leg too small for one MNQ at this base is not traded.
            return None, (f"size rounds to 0 contracts: base {base} MNQ units x leg weight "
                          f"{band.weight:g}")
        quantities = split(units)
        cap = self.config.max_quantity
        over = [f"{quantity} {root}" for root, quantity in quantities.items() if quantity > cap]
        if over:
            return None, f"order quantity {' and '.join(over)} exceeds risk.max_quantity {cap}"
        return quantities, {**quantities, "base": base, "units": units,
                            "weight": band.weight, "net_liquidation": equity, "reference_price": price,
                            "leverage_fraction": fraction, "at": now.isoformat()}

    def _screen_entries(self, actions: list[Action], now: datetime) -> list[Action]:
        """Check margin and stop risk once for every entry order of this decision."""
        entries = [action for action in actions
                   if isinstance(action, Place) and action.request.purpose == "entry"]
        if not entries:
            return actions
        refusal = self._entry_refusal([action.request for action in entries], now)
        if refusal is None:
            return actions
        screened: list[Action] = []
        for action in actions:
            if not any(action is entry for entry in entries):
                screened.append(action)
            elif action is entries[0]:
                screened.append(MarkTrade(action.trade_key or "", "refused", refusal))
        return screened

    # Actions ------------------------------------------------------------------

    def _execute(self, action: Action, now: datetime) -> None:
        if isinstance(action, MarkTrade):
            self.journal.mark_trade(action.trade_key, action.status, action.reason)
            self.journal.log("trade", {"trade": action.trade_key, "status": action.status,
                                       "reason": action.reason})
            LOGGER.info("trade %s: %s (%s)", action.trade_key, action.status, action.reason)
            if action.status in ("missed", "refused"):
                self.acks.send(action.status, self._seq(), {"reason": action.reason})
            return
        if isinstance(action, Halt):
            self._halt(action.reason)
            return
        try:
            if isinstance(action, Cancel):
                planned_state = (self.broker.state()
                                 if action.reason == "pre-open stop cancellation" else None)
                planned_target = self.target
                self.broker.cancel(action.order_id)
                if planned_state is not None:
                    self._protection.planned_cancellation(
                        planned_state, action.order_id, planned_target, now,
                        self.config.ibkr.client_id, self.config.clock_exit_grace_seconds,
                    )
                self.pending[action.order_id] = Pending("cancel", now)
                self.journal.log("cancel", {"order_id": action.order_id, "reason": action.reason})
                LOGGER.info("cancel order %s: %s", action.order_id, action.reason)
            elif isinstance(action, Modify):
                self.broker.place(action.request, action.order_id)
                self._record(action.order_id, action.request, self._trade_of(action.order_id))
                self.pending[action.order_id] = Pending(
                    "modify", now, "stop", action.request.stop_price, action.request.quantity
                )
                LOGGER.info("move stop %s to %s x%s", action.order_id, action.request.stop_price,
                            action.request.quantity)
            elif isinstance(action, Place):
                request = action.request
                order_id = self.broker.place(request)
                self._record(order_id, request, action.trade_key)
                self.pending[order_id] = Pending("place", now, request.purpose)
                self.acks.send("submitted", self._seq(), {"purpose": request.purpose})
                LOGGER.info("placed %s order %s: %s %s %s %s x%s lmt=%s stp=%s", request.purpose, order_id,
                            request.action, request.order_type, request.contract.root,
                            request.contract.contract_month, request.quantity, request.limit_price,
                            request.stop_price)
        except Exception as exc:  # noqa: BLE001 - the next step retries
            LOGGER.error("%s failed: %s", type(action).__name__, exc)
            self.journal.log("action_failed", {"action": type(action).__name__, "error": str(exc)})

    def _record(self, order_id: int, request: OrderRequest, trade_key: str | None) -> None:
        if self.config.sizing is not None:
            self._remember_root(request.contract)
        self.journal.record_order(
            order_id,
            trade_key=trade_key,
            purpose=request.purpose,
            con_id=request.contract.con_id,
            action=request.action,
            order_type=request.order_type,
            quantity=request.quantity,
            price=request.stop_price if request.order_type == "STP" else request.limit_price,
            order_ref=request.order_ref,
        )

    def _trade_of(self, order_id: int) -> str | None:
        return self.journal.order_trades().get(order_id)

    # Margin and risk ------------------------------------------------------------

    def _entry_refusal(self, requests: list[OrderRequest], now: datetime) -> str | None:
        """Stop risk and initial margin of every entry order together, before any is sent."""
        target = self.target
        entry = target.entry if target is not None else None
        limit = self.config.max_stop_risk_usd
        if limit is not None and entry is not None and entry.atr and entry.stop_atr:
            risk = sum(request.quantity * MULTIPLIERS[request.contract.root] for request in requests
                       ) * entry.atr * entry.stop_atr
            if risk > limit:
                return f"stop risk ${risk:,.0f} exceeds max_stop_risk_usd ${limit:,.0f}"
        estimates = [self._margin_estimate(request, now, allow_stale=False) for request in requests]
        if any(estimate is None for estimate in estimates):
            return "margin check unavailable"
        first, *others = estimates
        assert first is not None
        # Each what-if sees the account without the other order; add the others'
        # increments, or their whole margin when IBKR omits the figure before.
        init_after = first.init_margin_after + sum(
            other.init_margin_after - (other.init_margin_before or 0.0) for other in others if other)
        equity = min(estimate.equity_with_loan_after for estimate in estimates if estimate)
        ceiling = self.config.max_margin_fraction * equity
        if init_after > ceiling:
            return (
                f"initial margin after entry {init_after:,.0f} exceeds "
                f"{self.config.max_margin_fraction:.0%} of equity {equity:,.0f}"
            )
        return None

    def _margin_estimate(self, request: OrderRequest, now: datetime, *, allow_stale: bool) -> MarginEstimate | None:
        key = (request.contract.con_id, request.action, request.quantity)
        cached = self._margin.get(key)
        max_age = timedelta(seconds=self.config.margin_check_max_age_seconds)
        if cached is not None and (allow_stale or now - cached[0] <= max_age):
            return cached[1]
        try:
            estimate = self.broker.what_if(replace(request, order_type="MKT", limit_price=None))
        except Exception as exc:  # noqa: BLE001 - refuse the entry rather than guess
            self._warn_once("what_if", f"margin what-if failed: {exc}")
            return None
        self._margin[key] = (now, estimate)
        return estimate

    def _warm_margin(self, views: list[View], now: datetime) -> None:
        target = self.target
        if any(view.position for view in views) or target is None or not target.contract_month:
            return
        if target.direction and target.entry is not None and now <= target.entry.deadline:
            return
        if self.config.sizing is not None:
            # Quantities are only known at the entry; keep NetLiquidation fresh instead,
            # at most every 30 s even while IBKR cannot report it.
            if now - self._net_liquidation_warmed >= NET_LIQUIDATION_MAX_AGE / 2:
                self._net_liquidation_warmed = now
                self._net_liquidation_cache = None
                self._net_liquidation(now)
            return
        contract = self._contract(self.config.root, target.contract_month)
        if contract is None:
            return
        max_age = timedelta(seconds=self.config.margin_check_max_age_seconds)
        for action in ("BUY", "SELL"):
            key = (contract.con_id, action, self.config.quantity)
            cached = self._margin.get(key)
            if cached is None or now - cached[0] > max_age / 2:
                request = OrderRequest("entry", contract, action, "MKT", self.config.quantity, "fx:whatif:0")
                self._margin.pop(key, None)
                self._margin_estimate(request, now, allow_stale=False)
                return

    # Helpers ----------------------------------------------------------------------

    def _contract(self, root: str, month: str) -> FutureContract | None:
        if (root, month) in self._contracts:
            return self._contracts[(root, month)]
        try:
            contract = self.broker.resolve(root, month)
        except Exception as exc:  # noqa: BLE001 - retried on the next step
            self._warn_once(f"resolve:{root}:{month}", f"cannot resolve {root} {month}: {exc}")
            return None
        self._contracts[(root, month)] = contract
        return contract

    def _halt(self, reason: str) -> None:
        if self.journal.halt(reason):
            LOGGER.error("HALTED: %s", reason)
            self.acks.send("error", self._seq(), {"halted": True, "reason": reason})

    def _seq(self) -> int | None:
        return self.target.seq if self.target is not None else None

    def _watch_feed(self, now: datetime) -> None:
        last = self.last_heartbeat_at
        stale = (now - (last or self._started_at) > timedelta(seconds=self.config.heartbeat_timeout_seconds)
                 or (last is not None and self._heartbeat_seq > self.journal.last_seq()))
        if stale and not self._feed_stale:
            LOGGER.warning("no leader heartbeat for %.0f s; stops and exit plans stay in force",
                           (now - (last or self._started_at)).total_seconds())
        elif not stale and self._feed_stale:
            LOGGER.info("leader heartbeat recovered")
        self._feed_stale = stale
        if self.notifications is not None and (stale or last is not None):
            self.notifications.status("signal_feed", "unavailable" if stale else "ready", now,
                                      announce_initial=stale)

    def _state_ack(self, views: list[View], now: datetime, halt: str | None) -> None:
        if now < self._next_state_ack:
            return
        self._next_state_ack = now + STATE_ACK_INTERVAL
        position = sum(view.position for view in views)
        held = "flat" if position == 0 else ("long" if position > 0 else "short")
        target = views[0].target
        wanted = target.position if target is not None else "flat"
        age = None if self.last_heartbeat_at is None else round((now - self.last_heartbeat_at).total_seconds(), 1)
        self.acks.send("state", self._seq(), {"position": held, "matches_target": held == wanted,
                                              "halted": halt is not None, "heartbeat_age_seconds": age})

    def _warn_once(self, key: str, message: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            LOGGER.warning(message)

    def _load_target(self) -> Target | None:
        payload = self.journal.latest_payload()
        if payload is None:
            return None
        try:
            return parse_target(payload, self.config.stream)
        except SignalError:
            return None
