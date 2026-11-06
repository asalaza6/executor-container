# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from executor_support import Leader, contract, payload, write_config

from follow_executor.broker import BrokerState, MarginEstimate
from follow_executor.cli import command_check, quote_readiness


class QuoteReadinessTests(unittest.TestCase):
    def broker(self, status, codes=(), connected=True):
        return Mock(health=Mock(return_value={"connected": connected, "market_data": status}),
                    market_data_errors=Mock(return_value=list(codes)))

    def test_competing_session_has_actionable_advice_without_disconnecting_it(self):
        broker = self.broker("denied", [10197])
        result = quote_readiness(broker, object(), 0)
        self.assertEqual(result["codes"], [10197])
        self.assertIn("Log out of that session deliberately", result["message"])
        broker.disconnect.assert_not_called()
        broker.place.assert_not_called()

    def test_no_quote_does_not_claim_market_is_closed_or_ready(self):
        result = quote_readiness(self.broker("pending"), object(), 0)
        self.assertEqual(result["status"], "no_quote")
        self.assertIn("may be closed", result["message"])

    def test_missing_subscription_has_specific_advice_without_bypassing_quotes(self):
        broker = self.broker("denied", [354])
        result = quote_readiness(broker, object(), 0)
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["codes"], [354])
        self.assertIn("Market Data Subscriptions", result["message"])
        self.assertIn("Gateway login username", result["message"])
        broker.place.assert_not_called()
        for status, connected in (("ready", True), ("ready", False)):
            with self.subTest(status=status, connected=connected):
                result = quote_readiness(self.broker(status, [354], connected), object(), 0)
                self.assertNotIn("not subscribed", result["message"])

    def test_live_delayed_and_disconnected_are_distinct(self):
        for status, connected, expected in (("ready", True, "ready"), ("delayed", True, "delayed"),
                                             ("ready", False, "disconnected")):
            self.assertEqual(quote_readiness(self.broker(status, connected=connected), object(), 0)["status"], expected)

    def test_authenticated_account_without_live_quotes_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            leader = Leader()
            config = write_config(Path(directory), leader.public_key)
            response = Mock(headers={})
            response.read.return_value = json.dumps(leader.envelope(payload(1, "test", "flat"))).encode()
            broker = self.broker("denied", [10197])
            broker.managed_accounts = (config.ibkr.account,)
            broker.state.return_value = BrokerState(connected=True)
            broker.resolve.return_value = contract()
            broker.what_if.return_value = MarginEstimate(100, 10000)
            output = io.StringIO()
            with patch("urllib.request.urlopen") as urlopen, \
                    patch("follow_executor.ibkr.IBKRBroker", return_value=broker), \
                    contextlib.redirect_stdout(output):
                urlopen.return_value.__enter__.return_value = response
                code = command_check(config, skip_broker=False, quotes=True)
            report = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(report["readiness"]["account"], "authenticated")
            self.assertEqual(report["readiness"]["reconciliation"], "complete")
            self.assertEqual(report["readiness"]["market_data"]["status"], "denied", report["problems"])
            self.assertIn(10197, report["readiness"]["market_data"]["codes"])
            broker.place.assert_not_called()

    def test_cached_account_list_and_failed_snapshot_cannot_claim_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            config = write_config(Path(directory), Leader().public_key)
            broker = Mock(managed_accounts=(config.ibkr.account,), is_connected=False)
            broker.wait_for_snapshot.side_effect = RuntimeError("snapshot incomplete")
            output = io.StringIO()
            with patch("urllib.request.urlopen", side_effect=OSError("offline fixture")), \
                    patch("follow_executor.ibkr.IBKRBroker", return_value=broker), \
                    contextlib.redirect_stdout(output):
                code = command_check(config, skip_broker=False, quotes=True)
            readiness = json.loads(output.getvalue())["readiness"]
            self.assertEqual(code, 1)
            self.assertEqual(readiness["api"], "disconnected")
            self.assertEqual(readiness["account"], "unavailable")
            self.assertEqual(readiness["reconciliation"], "unavailable")
            broker.place.assert_not_called()

    def test_disconnect_after_successful_quote_still_blocks_start(self):
        with tempfile.TemporaryDirectory() as directory:
            leader = Leader()
            config = write_config(Path(directory), leader.public_key)
            response = Mock(headers={})
            response.read.return_value = json.dumps(leader.envelope(payload(1, "test", "flat"))).encode()
            broker = self.broker("ready")
            broker.managed_accounts = (config.ibkr.account,)
            broker.state.return_value = BrokerState(connected=True)
            broker.resolve.return_value = contract()
            broker.what_if.return_value = MarginEstimate(100, 10000)
            broker.is_connected = False  # Connection lost after the quote callback.
            output = io.StringIO()
            with patch("urllib.request.urlopen") as urlopen, \
                    patch("follow_executor.ibkr.IBKRBroker", return_value=broker), \
                    contextlib.redirect_stdout(output):
                urlopen.return_value.__enter__.return_value = response
                code = command_check(config, skip_broker=False, quotes=True)
            report = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(report["readiness"]["api"], "disconnected")
            self.assertTrue(any("disconnected before" in issue for issue in report["problems"]))

    def test_balance_check_reports_net_liquidation_split_and_book_margin(self):
        with tempfile.TemporaryDirectory() as directory:
            leader = Leader()
            config = write_config(Path(directory), leader.public_key)
            raw = json.loads((Path(directory) / "executor.json").read_text())
            raw.pop("instrument")
            raw["sizing"] = {"mode": "balance", "leverage_fraction": 0.5}
            (Path(directory) / "executor.json").write_text(json.dumps(raw))
            from follow_executor.config import load_config
            config = load_config(Path(directory) / "executor.json")
            response = Mock(headers={})
            response.read.return_value = json.dumps(leader.envelope(payload(1, "test", "flat"))).encode()
            broker = self.broker("ready")
            broker.managed_accounts = (config.ibkr.account,)
            broker.state.return_value = BrokerState(connected=True)
            broker.resolve.side_effect = lambda root, month: contract(month, root)
            broker.what_if.side_effect = lambda request: MarginEstimate(
                40_000.0 if request.contract.root == "NQ" else 52_000.0, 250_000.0, "",
                0.0 if request.contract.root == "NQ" else 40_000.0)
            broker.net_liquidation.return_value = 250_000.0
            broker.quote_price.return_value = 21000.0
            output = io.StringIO()
            with patch("urllib.request.urlopen") as urlopen, \
                    patch("follow_executor.ibkr.IBKRBroker", return_value=broker) as factory, \
                    contextlib.redirect_stdout(output):
                urlopen.return_value.__enter__.return_value = response
                code = command_check(config, skip_broker=False, quotes=True)
            report = json.loads(output.getvalue())
            self.assertEqual(code, 0, report["problems"])
            self.assertEqual(factory.call_args.args[1], ("NQ", "MNQ"))
            self.assertEqual(report["root"], "NQ+MNQ")
            self.assertEqual(report["sizing"]["base_units"], 17)
            self.assertEqual(report["sizing"]["price_source"], "live NQ quote")
            self.assertEqual([size["book"] for size in report["sizing"]["weights"]][:2], ["1 NQ + 7 MNQ", "1 NQ + 3 MNQ"])
            broker.net_liquidation.return_value = 20_000.0  # base 1 at f = 0.5
            broker.what_if.side_effect = lambda request: MarginEstimate(2_000.0, 20_000.0)
            output = io.StringIO()
            with patch("urllib.request.urlopen") as urlopen, \
                    patch("follow_executor.ibkr.IBKRBroker", return_value=broker), \
                    contextlib.redirect_stdout(output):
                urlopen.return_value.__enter__.return_value = response
                self.assertEqual(command_check(config, skip_broker=False, quotes=True), 0)
            small = json.loads(output.getvalue())["sizing"]
            self.assertEqual(small["weights"][-1]["book"], "no entry (rounds to 0 contracts)")
            self.assertEqual(small["weights"][0]["book"], "1 MNQ")
            broker.net_liquidation.return_value = 250_000.0
            broker.what_if.side_effect = lambda request: MarginEstimate(
                40_000.0 if request.contract.root == "NQ" else 52_000.0, 250_000.0, "",
                0.0 if request.contract.root == "NQ" else 40_000.0)
            self.assertEqual(report["margin"]["BUY"]["init_margin_after"], 52_000.0)
            self.assertEqual(set(report["contract"]), {"NQ", "MNQ"})
            broker.place.assert_not_called()
            broker.what_if.side_effect = lambda request: MarginEstimate(80_000.0, 250_000.0)
            output = io.StringIO()
            with patch("urllib.request.urlopen") as urlopen, \
                    patch("follow_executor.ibkr.IBKRBroker", return_value=broker), \
                    contextlib.redirect_stdout(output):
                urlopen.return_value.__enter__.return_value = response
                self.assertEqual(command_check(config, skip_broker=False, quotes=True), 1)
            self.assertTrue(any("max_margin_fraction" in issue for issue in json.loads(output.getvalue())["problems"]))
