# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""IBKR TWS API adapter for the executor (official ``ibapi`` client).

Install the official ``ibapi`` from the TWS API download, matching IB Gateway.
The adapter keeps a callback-fed copy of positions, orders,
executions and rejections for the executor's futures roots (one, or NQ and
MNQ with balance sizing) in one account, so the executor reads its state
without a broker round trip.
"""

from __future__ import annotations

import itertools
import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from .broker import (
    MULTIPLIERS,
    BrokerState,
    Execution,
    FutureContract,
    MarginEstimate,
    OrderRequest,
    OrderView,
    Rejection,
)
from .config import IBKRSettings

LOGGER = logging.getLogger(__name__)
UNSET_DOUBLE = 1.7976931348623157e308
INFORMATIONAL_CODES = frozenset({2104, 2106, 2107, 2108, 2158, 2109, 2100, 399, 202, 10349})
CANCEL_REFUSED_CODES = frozenset({161, 10147, 10148})
RECONNECT_CODES = frozenset({504, 1100, 1101, 1102, 1300, 2110})
# "Couldn't connect to TWS" and "Not connected" repeat on every retry while the
# Gateway is down; the executor logs the outage once and its recovery once.
NOT_CONNECTED_CODES = frozenset({502, 504})


class IBKRError(RuntimeError):
    pass


def _price(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number >= UNSET_DOUBLE or number == 0:
        return None
    return number


def _amount(value: Any) -> float | None:
    """Parse an IBKR what-if amount, which arrives as a string."""

    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) >= UNSET_DOUBLE:
        return None
    return number


class IBKRBroker:
    def __init__(
        self,
        settings: IBKRSettings,
        root: str | tuple[str, ...],
        *,
        on_update: Callable[[], None] | None = None,
    ) -> None:
        try:
            from ibapi.client import EClient
            from ibapi.wrapper import EWrapper
        except ImportError as exc:  # pragma: no cover - depends on the follower's install
            raise IBKRError(
                "the official IBKR Python client (ibapi) is not installed; install it from "
                "the TWS API release that matches IB Gateway"
            ) from exc
        self.settings = settings
        self.roots = (root,) if isinstance(root, str) else tuple(root)
        self.root = self.roots[0]
        self._on_update = on_update or (lambda: None)
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._managed_event = threading.Event()
        self._positions_end = threading.Event()
        self._orders_end = threading.Event()
        self._executions_end = threading.Event()
        self._execution_request_id = None
        self._snapshot_started = None
        self._snapshot_id = 0
        self._reconciled = False
        self._market_requests: dict[int, dict[str, Any]] = {}
        self._down_farms: set[str] = set()
        self._market_reset = False
        self._managed: tuple[str, ...] = ()
        self._next_id: int | None = None
        self._request_ids = itertools.count(1_000_000)
        self._rejection_seq = itertools.count(1)
        self._positions: dict[int, int] = {}
        self._average: dict[int, float] = {}
        self._contracts: dict[int, FutureContract] = {}
        self._orders: dict[int, OrderView] = {}
        self._statuses: dict[int, tuple[str, int]] = {}
        self._executions: dict[str, Execution] = {}
        self._rejections: list[Rejection] = []
        self._placed: set[int] = set()
        self._open_seen: set[int] | None = None
        self._details: dict[int, list[Any]] = {}
        self._detail_events: dict[int, threading.Event] = {}
        self._request_errors: dict[int, str] = {}
        self._what_if: dict[int, tuple[threading.Event, list[Any]]] = {}
        self._summaries: dict[int, tuple[threading.Event, list[Any]]] = {}
        owner = self

        class App(EWrapper, EClient):  # type: ignore[misc, valid-type]
            def __init__(self) -> None:
                EWrapper.__init__(self)
                EClient.__init__(self, self)

            def useProtoBuf(self, msgId: int) -> bool:
                from ibapi.message import OUT

                # Gateway server 226 accepts protobuf summary requests but does
                # not release their subscriptions on protobuf cancellation.
                # Keep every other message/version on the SDK's negotiated path.
                if msgId == OUT.CANCEL_ACCOUNT_SUMMARY and self.serverVersion() == 226:
                    return False
                return super().useProtoBuf(msgId)

            def nextValidId(self, orderId: int) -> None:
                with owner._lock:
                    owner._next_id = max(orderId, owner._next_id or 0)
                owner._ready.set()

            def managedAccounts(self, accountsList: str) -> None:
                owner._managed = tuple(a.strip() for a in accountsList.split(",") if a.strip())
                owner._managed_event.set()

            def position(self, account: str, contract: Any, position: Any, avgCost: float) -> None:
                owner.on_position(account, contract, position, avgCost)

            def positionEnd(self) -> None:
                owner._positions_end.set()

            def openOrder(self, orderId: int, contract: Any, order: Any, orderState: Any) -> None:
                owner.on_open_order(orderId, contract, order, orderState)

            def openOrderEnd(self) -> None:
                owner.on_open_order_end()
                owner._orders_end.set()

            def orderStatus(self, orderId: int, status: str, filled: Any, remaining: Any,
                            avgFillPrice: float, permId: int, parentId: int, lastFillPrice: float,
                            clientId: int, whyHeld: str, mktCapPrice: float = 0.0) -> None:
                owner.on_order_status(orderId, status, filled)

            def execDetails(self, reqId: int, contract: Any, execution: Any) -> None:
                owner.on_execution(contract, execution)

            def execDetailsEnd(self, reqId: int) -> None:
                if reqId == owner._execution_request_id:
                    owner._executions_end.set()
                    owner._on_update()

            def tickPrice(self, reqId: int, tickType: int, price: float, attrib: Any) -> None:
                owner.on_tick_price(reqId, tickType, price)

            def marketDataType(self, reqId: int, marketDataType: int) -> None:
                owner.on_market_data_type(reqId, marketDataType)

            def contractDetails(self, reqId: int, contractDetails: Any) -> None:
                owner._details.setdefault(reqId, []).append(contractDetails)

            def accountSummary(self, reqId: int, account: str, tag: str, value: str,
                               currency: str) -> None:
                pending = owner._summaries.get(reqId)
                if pending is not None:
                    pending[1].append((account, tag, value, currency))

            def accountSummaryEnd(self, reqId: int) -> None:
                pending = owner._summaries.get(reqId)
                if pending is not None:
                    pending[0].set()

            def contractDetailsEnd(self, reqId: int) -> None:
                event = owner._detail_events.get(reqId)
                if event is not None:
                    event.set()

            def error(self, reqId: int, errorTime: int, errorCode: int, errorString: str,
                      advancedOrderRejectJson: str = "") -> None:
                owner.on_error(reqId, errorCode, errorString)

            def connectionClosed(self) -> None:
                owner._ready.clear()
                owner._reconciled = False
                owner._on_update()

        self._app = App()
        self._thread: threading.Thread | None = None

    # Connection --------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return bool(self._app.isConnected() and self._ready.is_set())

    @property
    def managed_accounts(self) -> tuple[str, ...]:
        return self._managed

    def connect(self) -> None:
        if self._app.isConnected():
            self.disconnect()
        self._ready.clear()
        self._managed_event.clear()
        self._reconciled = False
        self._snapshot_started = None
        with self._lock:
            self._market_requests.clear()
            self._down_farms.clear()
        self._app.connect(self.settings.host, self.settings.port, self.settings.client_id)
        self._thread = threading.Thread(target=self._app.run, name="ibkr", daemon=True)
        self._thread.start()
        if not self._ready.wait(self.settings.timeout_seconds):
            raise IBKRError("timed out waiting for nextValidId")
        self._app.reqManagedAccts()
        if not self._managed_event.wait(self.settings.timeout_seconds):
            raise IBKRError("timed out waiting for managed accounts")

    def disconnect(self) -> None:
        self._app.disconnect()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=self.settings.timeout_seconds)
        self._ready.clear()
        self._reconciled = False

    def refresh(self) -> None:
        from ibapi.execution import ExecutionFilter

        now = time.monotonic()
        # Do not overwrite an unfinished reconciliation with another periodic request.
        if self._snapshot_started is not None and not self._snapshot_complete():
            if now - self._snapshot_started <= 3 * self.settings.timeout_seconds:
                return
            self._reconciled = False
        self._snapshot_started = now
        self._snapshot_id += 1
        self._positions_end.clear()
        self._orders_end.clear()
        self._executions_end.clear()
        with self._lock:
            self._open_seen = set()
        self._app.reqPositions()
        self._app.reqAllOpenOrders()
        execution_filter = ExecutionFilter()
        execution_filter.acctCode = self.settings.account
        execution_filter.secType = "FUT"
        # One root filters at the broker; a book filters each callback by root.
        execution_filter.symbol = self.root if len(self.roots) == 1 else ""
        self._execution_request_id = next(self._request_ids)
        self._app.reqExecutions(self._execution_request_id, execution_filter)

    def _snapshot_complete(self) -> bool:
        return all(event.is_set() for event in (self._positions_end, self._orders_end, self._executions_end))

    def wait_for_snapshot(self) -> None:
        for event in (self._positions_end, self._orders_end, self._executions_end):
            if not event.wait(self.settings.timeout_seconds):
                raise IBKRError("timed out waiting for complete IBKR positions/orders/executions")
        if not self.is_connected:
            raise IBKRError("IBKR disconnected during the positions/orders check")
        self._reconciled = True

    def monitor_market_data(self, contracts: list[FutureContract]) -> None:
        """Read-only streaming quotes for health checks; never used to price orders."""
        if not self.is_connected:
            return
        wanted = {contract.con_id: contract for contract in contracts}
        now = time.monotonic()
        with self._lock:
            for req_id, item in list(self._market_requests.items()):
                retry = item["status"] in {"denied", "unavailable", "delayed"} and now - item["since"] >= 60
                if item["contract"].con_id not in wanted or self._market_reset or retry:
                    self._market_requests.pop(req_id)
                    self._app.cancelMktData(req_id)
            self._market_reset = False
            existing = {item["contract"].con_id for item in self._market_requests.values()}
            for con_id, contract in wanted.items():
                if con_id in existing:
                    continue
                req_id = next(self._request_ids)
                self._market_requests[req_id] = {"contract": contract, "since": now,
                                                 "live": False, "quote": False, "status": "pending"}
                try:
                    self._app.reqMarketDataType(1)
                    # Streaming, not a paid regulatory snapshot; normal data entitlements apply.
                    self._app.reqMktData(req_id, self._contract(contract), "", False, False, [])
                except Exception:  # noqa: BLE001 - a failed health request remains retryable
                    self._market_requests[req_id]["status"] = "unavailable"

    def on_market_data_type(self, request_id: int, data_type: int) -> None:
        with self._lock:
            item = self._market_requests.get(request_id)
            if item is not None:
                item["live"] = data_type == 1
                if data_type != 1:
                    item["status"] = "delayed"
                elif item["quote"]:
                    item["status"] = "ready"
        self._on_update()

    def on_tick_price(self, request_id: int, tick_type: int, price: float) -> None:
        with self._lock:
            item = self._market_requests.get(request_id)
            if item is None or _price(price) is None or price <= 0:
                return
            if tick_type in {1, 2, 4}:  # bid, ask or last; ignore close/invalid quotes
                item["quote"] = True
                item.setdefault("prices", {})[tick_type] = float(price)
                if item["live"]:
                    item["status"] = "ready"
            elif tick_type in {66, 67, 68}:
                item["status"] = "delayed"
        self._on_update()

    def health(self) -> dict[str, Any]:
        with self._lock:
            connected = self.is_connected
            if connected and self._snapshot_complete():
                self._reconciled = True
            elif self._snapshot_started is not None and time.monotonic() - self._snapshot_started > 3 * self.settings.timeout_seconds:
                self._reconciled = False
            statuses = {item["status"] for item in self._market_requests.values()}
            if self._down_farms:
                market = "unavailable"
            elif self._market_reset:
                market = "pending"
            elif not statuses:
                market = "idle"
            else:
                market = next((value for value in ("denied", "unavailable", "delayed", "pending")
                               if value in statuses), "ready")
            return {"connected": connected, "reconciled": connected and self._reconciled,
                    "market_data": market}

    def quote_price(self, con_id: int) -> float | None:
        """Latest live last price, else bid/ask midpoint: size previews only, never orders."""
        with self._lock:
            for item in self._market_requests.values():
                prices = item.get("prices", {})
                if item["contract"].con_id != con_id or not item["live"] or not prices:
                    continue
                if 4 in prices:
                    return prices[4]
                if 1 in prices and 2 in prices:
                    return (prices[1] + prices[2]) / 2
        return None

    def market_data_errors(self) -> list[int]:
        """Return diagnostic codes only; never expose raw broker messages."""
        with self._lock:
            return sorted({item["error_code"] for item in self._market_requests.values()
                           if "error_code" in item})

    # Requests ----------------------------------------------------------------

    def resolve(self, root: str, contract_month: str) -> FutureContract:
        from ibapi.contract import Contract

        query = Contract()
        query.symbol = root
        query.secType = "FUT"
        query.exchange = "CME"
        query.currency = "USD"
        query.lastTradeDateOrContractMonth = contract_month
        request_id = next(self._request_ids)
        event = threading.Event()
        self._details[request_id] = []
        self._detail_events[request_id] = event
        self._app.reqContractDetails(request_id, query)
        try:
            if not event.wait(self.settings.timeout_seconds):
                raise IBKRError(f"timed out resolving {root} {contract_month}")
            error = self._request_errors.pop(request_id, None)
            if error is not None:
                raise IBKRError(error)
            details = self._details.get(request_id, [])
        finally:
            self._details.pop(request_id, None)
            self._detail_events.pop(request_id, None)
        contracts = {self._future(item.contract).con_id: self._future(item.contract) for item in details}
        if len(contracts) != 1:
            raise IBKRError(f"{root} {contract_month} resolved to {len(contracts)} contracts")
        contract = next(iter(contracts.values()))
        with self._lock:
            self._contracts[contract.con_id] = contract
        return contract

    def place(self, request: OrderRequest, order_id: int | None = None) -> int:
        if not self.is_connected:
            raise ConnectionError("IBKR is not connected")
        if order_id is None:
            order_id = self._take_order_id()
        with self._lock:
            self._placed.add(order_id)
        self._app.placeOrder(order_id, self._contract(request.contract), self._order(request))
        return order_id

    def cancel(self, order_id: int) -> None:
        from ibapi.order_cancel import OrderCancel

        if not self.is_connected:
            raise ConnectionError("IBKR is not connected")
        self._app.cancelOrder(order_id, OrderCancel())

    def what_if(self, request: OrderRequest) -> MarginEstimate:
        if not self.is_connected:
            raise ConnectionError("IBKR is not connected")
        order_id = self._take_order_id()
        order = self._order(request)
        order.whatIf = True
        event = threading.Event()
        holder: list[Any] = []
        self._what_if[order_id] = (event, holder)
        try:
            self._app.placeOrder(order_id, self._contract(request.contract), order)
            if not event.wait(self.settings.timeout_seconds):
                raise IBKRError("timed out waiting for the what-if margin estimate")
        finally:
            self._what_if.pop(order_id, None)
        if not holder or isinstance(holder[0], str):
            raise IBKRError(holder[0] if holder else "no what-if response")
        state = holder[0]
        init_after = _amount(state.initMarginAfter)
        equity_after = _amount(state.equityWithLoanAfter)
        if init_after is None or equity_after is None:
            raise IBKRError("the what-if response carries no margin figures")
        return MarginEstimate(init_after, equity_after, str(getattr(state, "warningText", "") or ""),
                              _amount(getattr(state, "initMarginBefore", None)))

    def net_liquidation(self) -> float:
        if not self.is_connected:
            raise ConnectionError("IBKR is not connected")
        request_id = next(self._request_ids)
        event = threading.Event()
        rows: list[Any] = []
        self._summaries[request_id] = (event, rows)
        try:
            self._app.reqAccountSummary(request_id, "All", "NetLiquidation")
            if not event.wait(self.settings.timeout_seconds):
                raise IBKRError("timed out waiting for NetLiquidation")
        finally:
            self._summaries.pop(request_id, None)
            try:
                self._app.cancelAccountSummary(request_id)
            except Exception as exc:  # noqa: BLE001 - the summary request is finished either way
                LOGGER.debug("account summary cancel failed: %s", exc)
        for row in rows:
            if isinstance(row, str):
                raise IBKRError(row)
        for account, tag, value, currency in rows:
            if account != self.settings.account or tag != "NetLiquidation":
                continue
            if currency != "USD":
                raise IBKRError(f"NetLiquidation is reported in {currency}, not USD")
            amount = _amount(value)
            if amount is None or amount <= 0:
                raise IBKRError("NetLiquidation is unavailable")
            return amount
        raise IBKRError("NetLiquidation was not reported for the configured account")

    def state(self) -> BrokerState:
        with self._lock:
            return BrokerState(
                connected=self.is_connected,
                positions=dict(self._positions),
                average_prices=dict(self._average),
                contracts=dict(self._contracts),
                orders=dict(self._orders),
                executions=tuple(self._executions.values()),
                rejections=tuple(self._rejections),
                as_of=datetime.now(UTC),
                snapshot_id=self._snapshot_id,
                snapshot_complete=self._snapshot_complete(),
            )

    # Callbacks (IBKR reader thread; also called directly by tests) -----------

    def on_position(self, account: str, contract: Any, position: Any, average_cost: float) -> None:
        if account != self.settings.account or contract.secType != "FUT" or contract.symbol not in self.roots:
            return
        future = self._future(contract)
        with self._lock:
            self._contracts[future.con_id] = future
            self._positions[future.con_id] = int(float(position))
            if float(position) and average_cost:
                self._average[future.con_id] = float(average_cost) / future.multiplier
            else:
                self._average.pop(future.con_id, None)
        self._on_update()

    def on_open_order(self, order_id: int, contract: Any, order: Any, order_state: Any) -> None:
        if getattr(order, "whatIf", False):
            pending = self._what_if.get(order_id)
            if pending is not None:
                pending[1].append(order_state)
                pending[0].set()
            return
        if contract.symbol not in self.roots or contract.secType != "FUT":
            return
        if order.account and order.account != self.settings.account:
            return
        with self._lock:
            status, filled = self._statuses.get(order_id, (str(order_state.status), 0))
            status = str(order_state.status) or status
            self._orders[order_id] = OrderView(
                order_id=order_id,
                con_id=int(contract.conId),
                root=str(contract.symbol),
                action=str(order.action),
                order_type=str(order.orderType),
                quantity=int(float(order.totalQuantity)),
                filled=filled,
                status=status,
                order_ref=str(order.orderRef or ""),
                client_id=int(order.clientId),
                stop_price=_price(order.auxPrice) if order.orderType == "STP" else None,
                limit_price=_price(order.lmtPrice) if order.orderType == "LMT" else None,
            )
            if self._open_seen is not None:
                self._open_seen.add(order_id)
        self._on_update()

    def on_open_order_end(self) -> None:
        with self._lock:
            seen, self._open_seen = self._open_seen, None
            if seen is None:
                return
            for order_id, order in list(self._orders.items()):
                if order.working and order_id not in seen:
                    # Not open at the broker any more: filled or cancelled while unseen.
                    self._orders[order_id] = replace(order, status="Absent")
        self._on_update()

    def on_order_status(self, order_id: int, status: str, filled: Any) -> None:
        with self._lock:
            count = int(float(filled or 0))
            self._statuses[order_id] = (str(status), count)
            order = self._orders.get(order_id)
            if order is not None:
                self._orders[order_id] = replace(order, status=str(status), filled=count)
        self._on_update()

    def on_execution(self, contract: Any, execution: Any) -> None:
        if contract.symbol not in self.roots or execution.acctNumber != self.settings.account:
            return
        item = Execution(
            exec_id=str(execution.execId),
            order_id=int(execution.orderId),
            con_id=int(contract.conId),
            side=str(execution.side),
            quantity=int(float(execution.shares)),
            price=float(execution.price),
            order_ref=str(execution.orderRef or ""),
            time=str(execution.time),
        )
        with self._lock:
            self._executions[item.exec_id] = item
        self._on_update()

    def on_error(self, request_id: int, code: int, message: str) -> None:
        if code in {2103, 2104}:
            # Match farm names locally; neither names nor raw error strings leave the VM.
            farm = message.rsplit(":", 1)[-1].strip()
            with self._lock:
                if code == 2103:
                    self._down_farms.add(farm)
                elif farm in self._down_farms:
                    self._down_farms.discard(farm)
                    self._market_reset = True  # New request IDs require new quote confirmation.
            self._on_update()
        with self._lock:
            market = self._market_requests.get(request_id)
            if market is not None and code not in INFORMATIONAL_CODES:
                market["error_code"] = code
                market["status"] = ("denied" if code in {354, 10089, 10090, 10167, 10168, 10186, 10197}
                                    else "unavailable")
                market["quote"] = False
                self._on_update()
                return
        if code in INFORMATIONAL_CODES:
            LOGGER.debug("IBKR %s %s: %s", request_id, code, message)
            return
        quiet = code in NOT_CONNECTED_CODES and request_id < 0
        (LOGGER.debug if quiet else LOGGER.warning)("IBKR %s %s: %s", request_id, code, message)
        if request_id in self._what_if:
            event, holder = self._what_if[request_id]
            holder.append(f"what-if rejected ({code}): {message}")
            event.set()
            return
        if request_id in self._summaries:
            event, holder = self._summaries[request_id]
            holder.append(f"account summary refused ({code}): {message}")
            event.set()
            return
        if request_id in self._detail_events:
            self._request_errors[request_id] = f"IBKR {code}: {message}"
            self._detail_events[request_id].set()
            return
        if code in RECONNECT_CODES:
            self._ready.clear()
            self._reconciled = False
            with self._lock:
                self._market_requests.clear()
        if request_id in self._placed or request_id in self._orders:
            with self._lock:
                self._rejections.append(
                    Rejection(next(self._rejection_seq), request_id, code, message,
                              cancel_refused=code in CANCEL_REFUSED_CODES)
                )
                del self._rejections[:-200]
        self._on_update()

    # Helpers -----------------------------------------------------------------

    def _take_order_id(self) -> int:
        with self._lock:
            if self._next_id is None:
                raise IBKRError("nextValidId has not been received")
            order_id = self._next_id
            self._next_id += 1
            return order_id

    def _order(self, request: OrderRequest) -> Any:
        from ibapi.order import Order

        order = Order()
        order.account = self.settings.account
        order.action = request.action
        order.orderType = request.order_type
        order.totalQuantity = request.quantity
        order.tif = request.tif
        order.outsideRth = request.outside_rth
        order.orderRef = request.order_ref
        order.transmit = True
        if request.limit_price is not None:
            order.lmtPrice = request.limit_price
        if request.stop_price is not None:
            order.auxPrice = request.stop_price
        return order

    @staticmethod
    def _contract(contract: FutureContract) -> Any:
        from ibapi.contract import Contract

        value = Contract()
        value.conId = contract.con_id
        value.symbol = contract.root
        value.secType = "FUT"
        value.exchange = "CME"
        value.currency = "USD"
        value.lastTradeDateOrContractMonth = contract.last_trade_date
        return value

    def _future(self, contract: Any) -> FutureContract:
        expiry = str(contract.lastTradeDateOrContractMonth)
        try:
            multiplier = float(contract.multiplier)
        except (TypeError, ValueError):
            multiplier = MULTIPLIERS.get(str(contract.symbol), 1.0)
        return FutureContract(
            con_id=int(contract.conId),
            root=str(contract.symbol),
            contract_month=expiry[:6],
            last_trade_date=expiry,
            multiplier=multiplier or MULTIPLIERS.get(str(contract.symbol), 1.0),
        )
