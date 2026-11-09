# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Balance sizing: signal weights, the leverage band and the NQ + MNQ book."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from executor_support import (
    T0,
    Clock,
    FakeBroker,
    Leader,
    RecordingAcks,
    contract,
    payload,
    target,
    write_config,
)

from follow_executor.broker import MarginEstimate
from follow_executor.config import ConfigError, load_config, parse_config
from follow_executor.executor import Executor, public_ack
from follow_executor.journal import Journal
from follow_executor.local import settings_identity
from follow_executor.notifications import Notifications
from follow_executor.signal import Sizing, parse_target
from follow_executor.sizing import (
    LEADER_BAND,
    balance_base,
    book_label,
    leg_units,
    preview,
    preview_text,
    split,
)

PREOPEN = datetime(2026, 10, 2, 13, 29, tzinfo=UTC)
OPEN = datetime(2026, 10, 2, 13, 30, tzinfo=UTC)
PRICE = 21000.0
# A neutral leg name: sizing depends only on the weight each signal carries.
LEG = "example"


def band(weight: float = 1.0, **changes: float) -> dict[str, float]:
    values = {"weight": weight, "target_leverage": 6.0, "add_max_leverage": 5.88, "hold_max_leverage": 6.6}
    return values | changes


class BaseArithmeticTests(unittest.TestCase):
    def test_first_base_is_floor_of_scaled_target_over_two_times_price(self) -> None:
        # 6 x 1.0 x 100,000 / (2 x 20,000) = 15; at f = 0.5 it is 7.5 -> 7.
        self.assertEqual(balance_base(None, 100_000, 20_000, 1.0, LEADER_BAND), 15)
        self.assertEqual(balance_base(None, 100_000, 20_000, 0.5, LEADER_BAND), 7)
        self.assertEqual(balance_base(None, 6_000, 20_000, 1.0, LEADER_BAND), 0)

    def test_band_keeps_resets_and_adds_one_unit_at_a_time(self) -> None:
        # Inside 5.88x-6.6x the base is kept.
        self.assertEqual(balance_base(15, 100_000, 20_000, 1.0, LEADER_BAND), 15)
        # 15 x 40,000 > 6.6 x 90,000: reset to floor(6 x 90,000 / 40,000) = 13.
        self.assertEqual(balance_base(15, 90_000, 20_000, 1.0, LEADER_BAND), 13)
        # From 13, add while (n + 1) x 40,000 <= 588,000: 14 fits, 15 does not.
        self.assertEqual(balance_base(13, 100_000, 20_000, 1.0, LEADER_BAND), 14)
        # A balance increase never adds past the add ceiling.
        self.assertEqual(balance_base(10, 200_000, 20_000, 1.0, LEADER_BAND), 29)

    def test_exact_band_boundaries(self) -> None:
        # (n + 1) x N == 5.88 x f x E adds: 14 x 42,000 = 588,000.
        self.assertEqual(balance_base(13, 100_000, 21_000, 1.0, LEADER_BAND), 14)
        self.assertEqual(balance_base(14, 100_000, 21_000, 1.0, LEADER_BAND), 14)
        # n x N == 6.6 x f x E is kept: 33 x 40,000 = 1,320,000; one dollar less resets.
        self.assertEqual(balance_base(33, 200_000, 20_000, 1.0, LEADER_BAND), 33)
        self.assertEqual(balance_base(33, 199_999, 20_000, 1.0, LEADER_BAND), 29)
        # The first base: 6 x 0.7 x 100,000 = 420,000 = 10 x 42,000 exactly.
        self.assertEqual(balance_base(None, 100_000, 21_000, 0.7, LEADER_BAND), 10)

    def test_fraction_scales_the_band_from_the_signal(self) -> None:
        signal_band = Sizing(1.0, 4.0, 3.9, 4.4)
        self.assertEqual(balance_base(None, 100_000, 20_000, 1.0, signal_band), 10)
        self.assertEqual(balance_base(None, 100_000, 20_000, 0.25, signal_band), 2)
        self.assertEqual(balance_base(10, 100_000, 20_000, 0.5, signal_band), 5)  # 10 x N > 2.2 x E

    def test_units_round_half_up_with_no_minimum(self) -> None:
        self.assertEqual(leg_units(15, 0.5), 8)  # 7.5
        self.assertEqual(leg_units(15, 0.65), 10)  # 9.75
        self.assertEqual(leg_units(17, 0.4), 7)  # 6.8
        # The operator's examples: a small account skips trades that round to 0.
        self.assertEqual(leg_units(1, 0.4), 0)
        self.assertEqual(leg_units(1, 0.65), 1)
        self.assertEqual(leg_units(2, 0.4), 1)
        self.assertEqual(leg_units(1, 0.9), 1)
        self.assertEqual(leg_units(0, 1.0), 0)

    def test_split_and_label(self) -> None:
        self.assertEqual(split(23), {"NQ": 2, "MNQ": 3})
        self.assertEqual(split(7), {"NQ": 0, "MNQ": 7})
        self.assertEqual(book_label({"NQ": 1, "MNQ": 5}), "1 NQ + 5 MNQ")
        self.assertEqual(book_label({"NQ": 2, "MNQ": 0}), "2 NQ")
        self.assertEqual(book_label({}), "flat")

    def test_preview_marks_weights_that_round_to_zero(self) -> None:
        # 10,000 at f = 1 and NQ 21,000: base floor(60,000 / 42,000) = 1.
        base, sizes = preview(1.0, 10_000, PRICE)
        self.assertEqual(base, 1)
        self.assertEqual([size.units for size in sizes], [1, 1, 1, 0])
        text = preview_text(1.0, 10_000, PRICE, 10)
        self.assertIn("  weight 0.25 -> no entry (rounds to 0 contracts)", text)
        self.assertIn("round to 0 contracts at this balance; trades with those weights are skipped", text)
        self.assertNotIn("skipped", preview_text(0.5, 250_000, PRICE, 10))

    def test_preview_lists_each_example_weight(self) -> None:
        base, sizes = preview(0.5, 250_000, PRICE)
        self.assertEqual(base, 17)
        self.assertEqual([(size.weight, size.book) for size in sizes],
                         [(1.0, "1 NQ + 7 MNQ"), (0.75, "1 NQ + 3 MNQ"), (0.5, "9 MNQ"), (0.25, "4 MNQ")])


class SignalSizingTests(unittest.TestCase):
    def test_sizing_and_minutes_before_open_are_parsed(self) -> None:
        plan = {"rule": "next_rth_open", "cancel_stop_at": "2026-10-02T13:27:00+00:00",
                "flatten_at": "2026-10-02T13:28:00+00:00", "minutes_before_open": "2"}
        signal = target(1, "entry", sizing=band(0.55), plan=plan)
        self.assertEqual(signal.sizing, Sizing(0.55, 6.0, 5.88, 6.6))
        self.assertEqual(signal.exit_plan.minutes_before_open, 2)
        self.assertIsNone(target(1, "entry").sizing)

    def test_unusable_sizing_never_hides_the_stop(self) -> None:
        for bad in (band(0), band(1.2), band(True), band("0.5"), band(add_max_leverage=6.1),
                    band(hold_max_leverage=5.9), band(target_leverage=float("nan")), "weights", None):
            with self.subTest(bad=bad):
                text = json.loads(payload(2, "protective_stop_installed", stop=30100.0))
                text["target"]["sizing"] = bad
                signal = parse_target(json.dumps(text), "sessioncycle.mnq")
                self.assertIsNone(signal.sizing)
                self.assertEqual(signal.stop, 30100.0)

    def test_flat_targets_and_older_events_have_no_sizing(self) -> None:
        self.assertIsNone(target(3, "exit", "flat").sizing)


def balance_raw(fraction=0.5, **extra):
    raw = {
        "relay_url": "https://relay.example.com", "stream": "sessioncycle.mnq",
        "leader_public_key": Leader().public_key, "token_path": "/tmp/token",
        "journal_path": "/tmp/journal.sqlite3",
        "ibkr": {"port": 4002, "account": "DU1234567", "account_type": "paper"},
        "sizing": {"mode": "balance", "leverage_fraction": fraction},
    }
    return raw | extra


class BalanceConfigTests(unittest.TestCase):
    def test_balance_config_trades_both_roots(self) -> None:
        config = parse_config(balance_raw())
        self.assertEqual(config.roots, ("NQ", "MNQ"))
        self.assertEqual(config.size_label, "BALANCE 0.5")
        self.assertEqual(config.sizing.leverage_fraction, 0.5)
        self.assertEqual(parse_config(balance_raw(1)).size_label, "BALANCE 1")

    def test_fraction_must_be_above_zero_and_at_most_one(self) -> None:
        for bad in (0, -0.5, 1.01, "0.5", True, None, float("inf")):
            with self.subTest(bad=bad), self.assertRaisesRegex(ConfigError, "leverage_fraction"):
                parse_config(balance_raw(bad))

    def test_balance_block_is_strict(self) -> None:
        for sizing in ({"mode": "fixed", "leverage_fraction": 0.5}, {"mode": "balance"},
                       {"mode": "balance", "leverage_fraction": 0.5, "extra": 1}, "balance"):
            with self.subTest(sizing=sizing), self.assertRaises(ConfigError):
                parse_config(balance_raw() | {"sizing": sizing})
        with self.assertRaisesRegex(ConfigError, "instrument"):
            parse_config(balance_raw(instrument={"root": "MNQ", "quantity": 1}))

    def test_fixed_config_identity_matches_earlier_releases(self) -> None:
        raw = balance_raw()
        del raw["sizing"]
        raw["instrument"] = {"root": "MNQ", "quantity": 2}
        config = parse_config(raw)
        self.assertIsNone(config.sizing)
        self.assertEqual(config.roots, ("MNQ",))
        self.assertEqual(config.size_label, "2 MNQ")
        legacy = json.dumps({"account": "DU1234567", "account_type": "paper", "client_id": 71,
                             "host": "127.0.0.1", "port": 4002, "root": "MNQ", "quantity": 2,
                             "stream": "sessioncycle.mnq", "leader_public_key": raw["leader_public_key"]},
                            sort_keys=True)
        self.assertEqual(settings_identity(config), legacy)
        self.assertNotEqual(settings_identity(parse_config(balance_raw())), legacy)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "deploy").is_dir(), "source checkout only")
    def test_example_configs_load(self) -> None:
        deploy = Path(__file__).resolve().parents[1] / "deploy"
        self.assertIsNone(load_config(deploy / "executor.example.json").sizing)
        self.assertEqual(load_config(deploy / "executor.balance.example.json").size_label, "BALANCE 0.5")


class BookTestCase(unittest.TestCase):
    fraction = 0.5

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.leader = Leader()
        self.clock = Clock()
        self.broker = FakeBroker()
        self.broker.market = PRICE
        self.acks = RecordingAcks()
        self.make()

    def make(self, **changes) -> None:
        directory = Path(self.directory.name)
        write_config(directory, self.leader.public_key)
        raw = json.loads((directory / "executor.json").read_text())
        raw.pop("instrument")
        raw["sizing"] = {"mode": "balance", "leverage_fraction": self.fraction}
        for dotted, value in changes.items():
            section, _, key = dotted.partition("__")
            raw.setdefault(section, {})[key] = value
        (directory / "executor.json").write_text(json.dumps(raw))
        self.config = load_config(directory / "executor.json")
        self.journal = Journal(self.config.journal_path)
        self.addCleanup(self.journal.close)
        self.executor = Executor(self.config, broker=self.broker, journal=self.journal,
                                 acks=self.acks, clock=self.clock)

    def restart(self) -> None:
        self.executor = Executor(self.config, broker=self.broker, journal=self.journal,
                                 acks=self.acks, clock=self.clock)

    def settle(self, steps: int = 6) -> None:
        for _ in range(steps):
            self.executor.step()
            self.clock.advance(0.1)

    def entry(self, seq=1, weight=1.0, **kwargs):
        kwargs.setdefault("leg", LEG)
        kwargs.setdefault("reference", PRICE)
        kwargs.setdefault("sizing", band(weight))
        return target(seq, "entry", **kwargs)

    def stops(self):
        return sorted((o.root, o.quantity, o.stop_price) for o in self.broker.working("stop"))

    def entries(self):
        return sorted((r.contract.root, r.quantity, r.order_type, r.limit_price)
                      for r in self.broker.placed("entry"))


class BookEntryTests(BookTestCase):
    def test_both_contracts_enter_at_the_same_decision_with_one_stop_each(self) -> None:
        signal = self.entry()
        self.executor.on_signal(signal)
        self.executor.step()
        # 6 x 0.5 x 250,000 / 42,000 = 17.86 -> base 17 -> 1 NQ + 7 MNQ.
        self.assertEqual(self.entries(), [("MNQ", 7, "LMT", 21010.0), ("NQ", 1, "LMT", 21010.0)])
        self.settle()
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 7})
        self.assertEqual(self.journal.trade_status(signal.trade_key), "entered")
        self.assertEqual(len(self.journal.expected_positions()), 2)
        self.assertEqual(self.executor.book(self.broker.state()), "1 NQ + 7 MNQ")
        self.assertEqual([stop[:2] for stop in self.stops()], [("MNQ", 7), ("NQ", 1)])

        self.executor.on_signal(target(2, "protective_stop_installed", stop=20900.0, reference=PRICE,
                                       sizing=band()))
        self.settle()
        self.assertEqual(self.stops(), [("MNQ", 7, 20900.0), ("NQ", 1, 20900.0)])
        self.executor.on_signal(target(3, "protective_stop_tightened", stop=20950.25, reference=PRICE,
                                       sizing=band()))
        self.settle()
        self.assertEqual(self.stops(), [("MNQ", 7, 20950.25), ("NQ", 1, 20950.25)])
        self.assertEqual(len(self.broker.placed("stop")), 2)

    def test_weight_sets_units_and_small_trades_use_only_mnq(self) -> None:
        self.executor.on_signal(self.entry(weight=0.4))  # 17 x 0.4 = 6.8 -> 7 MNQ
        self.settle()
        self.assertEqual(self.entries(), [("MNQ", 7, "LMT", 21010.0)])
        self.assertEqual(self.broker.held(), {"MNQ": 7})
        self.assertEqual([stop[:2] for stop in self.stops()], [("MNQ", 7)])

    def test_leader_flat_exits_both_and_closes_once_flat(self) -> None:
        signal = self.entry()
        self.executor.on_signal(signal)
        self.settle()
        self.executor.on_signal(target(2, "exit", "flat"))
        self.settle(10)
        self.assertEqual(self.broker.held(), {})
        self.assertEqual(sorted((r.contract.root, r.quantity) for r in self.broker.placed("exit")),
                         [("MNQ", 7), ("NQ", 1)])
        self.assertEqual(self.broker.working("stop"), [])
        self.assertEqual(self.journal.halt_reason(), None)

    def test_flatten_fallback_exits_both_contracts(self) -> None:
        signal = self.entry()
        self.executor.on_signal(signal)
        self.settle()
        self.clock.now = OPEN + timedelta(seconds=31)
        self.settle(10)
        self.assertEqual(self.broker.held(), {})
        self.assertEqual(self.journal.trade_status(signal.trade_key), "closed")

    def test_one_stop_fill_leaves_the_other_contract_protected_until_its_scheduled_exit(self) -> None:
        signal = self.entry()
        self.executor.on_signal(signal)
        self.settle()
        self.executor.on_signal(target(2, "protective_stop_installed", stop=20900.0, reference=PRICE,
                                       sizing=band()))
        self.settle()
        self.broker.trigger_stop("NQ")
        self.settle(10)
        self.assertEqual(self.broker.held(), {"MNQ": 7})
        self.assertEqual(self.stops(), [("MNQ", 7, 20900.0)])
        self.assertIsNone(self.journal.halt_reason())
        self.assertEqual(self.entries(), [("MNQ", 7, "LMT", 21010.0), ("NQ", 1, "LMT", 21010.0)])

        self.clock.now = PREOPEN
        self.settle()
        self.assertEqual(self.broker.working("stop"), [])
        self.clock.now = OPEN + timedelta(seconds=10)
        self.settle()
        self.assertEqual(self.broker.held(), {"MNQ": 7})  # the planned exception holds until the exit
        self.clock.now = OPEN + timedelta(seconds=31)
        self.settle(10)
        self.assertEqual(self.broker.held(), {})
        self.assertEqual([(r.contract.root, r.quantity) for r in self.broker.placed("exit")], [("MNQ", 7)])

    def test_preopen_cancel_records_each_contract_for_both_rule_names(self) -> None:
        for rule in ("next_rth_open", "before_next_rth_open"):
            with self.subTest(rule=rule):
                self.setUp()
                plan = {"rule": rule, "cancel_stop_at": PREOPEN.isoformat(), "flatten_at": OPEN.isoformat(),
                        "minutes_before_open": "1"}
                self.executor.on_signal(self.entry(plan=plan))
                self.settle()
                self.clock.now = PREOPEN
                self.settle()
                watch = json.loads(self.journal.get_state("protection_watch"))
                self.assertEqual(len([r for r in watch.values() if "planned_cancel" in r]), 2)
                self.clock.now = OPEN + timedelta(seconds=10)
                self.settle()
                self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 7})
                self.clock.now = OPEN + timedelta(seconds=31)
                self.settle(10)
                self.assertEqual(self.broker.held(), {})


class BookSizingRuleTests(BookTestCase):
    def test_band_is_persisted_and_reused_between_trades(self) -> None:
        self.executor.on_signal(self.entry())
        self.settle()
        self.assertEqual(json.loads(self.journal.get_state("balance_base"))["base"], 17)
        self.executor.on_signal(target(2, "exit", "flat"))
        self.settle(10)
        # 5% lower: 17 x 42,000 = 714,000 <= 6.6 x 0.5 x 237,500; keep 17, not floor(16.96).
        self.broker.net_liq = 237_500.0
        self.clock.advance(120)
        second = self.entry(3, signal_time=T0 + timedelta(hours=1), emitted=self.clock.now)
        self.executor.on_signal(second)
        self.settle()
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 7})
        self.assertEqual(json.loads(self.journal.get_state("balance_base"))["base"], 17)

    def test_unavailable_net_liquidation_reuses_the_last_base_or_refuses(self) -> None:
        self.broker.net_liq_error = ConnectionError("summary unavailable")
        first = self.entry()
        self.executor.on_signal(first)
        self.settle()
        self.assertEqual(self.journal.trade_status(first.trade_key), "refused")
        self.assertEqual(self.broker.placed("entry"), [])
        self.assertIn(("rejected", {"outcome": "refused", "reason": "sizing_unavailable"}),
                      [public_ack(kind, detail) for kind, _seq, detail in self.acks.sent])

        self.journal.set_state("balance_base", json.dumps({"base": 12}))
        second = self.entry(2, signal_time=T0 + timedelta(minutes=5), emitted=self.clock.now)
        self.executor.on_signal(second)
        self.settle()
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 2})

    def test_account_value_health_records_failure_and_recovery_without_guessing_size(self) -> None:
        self.broker.net_liq_error = TimeoutError("summary timed out")
        self.assertIsNone(self.executor._net_liquidation(self.clock()))
        failed = json.loads(self.journal.get_state("sizing_health"))
        self.assertEqual(failed["status"], "unavailable")
        self.assertIn("checked_at", failed)
        self.assertIsNone(self.journal.get_state("balance_base"))
        self.broker.net_liq_error = None
        self.clock.advance(30)
        self.assertGreater(self.executor._net_liquidation(self.clock()), 0)
        recovered = json.loads(self.journal.get_state("sizing_health"))
        self.assertEqual(recovered["status"], "ready")
        self.assertNotEqual(recovered["checked_at"], failed["checked_at"])

    def test_net_liquidation_warmup_is_throttled_while_ibkr_cannot_report_it(self) -> None:
        self.broker.net_liq_error = TimeoutError("summary timed out")
        self.executor.on_signal(target(1, "exit", "flat"))
        self.settle(100)  # ten seconds of loop steps
        self.assertEqual(self.broker.calls.count(("net_liquidation", None)), 1)
        self.clock.advance(30)
        self.settle(1)
        self.assertEqual(self.broker.calls.count(("net_liquidation", None)), 2)

    def test_a_small_book_never_resolves_nq(self) -> None:
        self.executor.on_signal(self.entry(weight=0.4))
        self.settle()
        self.assertEqual(self.broker.held(), {"MNQ": 7})
        self.assertEqual({c.root for c in self.broker.contracts.values()}, {"MNQ"})

    def test_missing_reference_price_reuses_the_last_base(self) -> None:
        self.journal.set_state("balance_base", json.dumps({"base": 9}))
        self.executor.on_signal(self.entry(reference=None))
        self.settle()
        self.assertEqual(self.broker.held(), {"MNQ": 9})
        self.assertEqual(self.entries()[0][2], "MKT")

    def test_signal_without_sizing_is_refused(self) -> None:
        signal = self.entry(sizing=None)
        self.executor.on_signal(signal)
        self.settle()
        self.assertEqual(self.journal.trade_status(signal.trade_key), "refused")
        self.assertEqual(self.broker.placed("entry"), [])

    def test_zero_base_is_refused_with_a_reason(self) -> None:
        self.broker.net_liq = 5_000.0
        signal = self.entry()
        self.executor.on_signal(signal)
        self.settle()
        self.assertEqual(self.journal.trade_status(signal.trade_key), "refused")
        reason = self.journal.recent("trades", 1)[0]["reason"]
        self.assertTrue(reason.startswith("balance base is 0"), reason)
        self.assertIsNone(self.journal.get_state("balance_base"))

    def test_a_trade_that_rounds_to_zero_is_refused_without_an_order(self) -> None:
        self.broker.net_liq = 20_000.0  # 3 x 20,000 / 42,000 -> base 1
        small = self.entry(weight=0.4)
        self.executor.on_signal(small)
        self.settle()
        self.assertEqual(self.journal.trade_status(small.trade_key), "refused")
        self.assertEqual(self.journal.recent("trades", 1)[0]["reason"],
                         "size rounds to 0 contracts: base 1 MNQ units x leg weight 0.4")
        self.assertEqual(self.broker.placed("entry"), [])
        self.assertEqual(self.broker.held(), {})
        self.assertEqual(json.loads(self.journal.get_state("balance_base"))["base"], 1)
        self.assertIn(("rejected", {"outcome": "refused", "reason": "size_rounds_to_zero"}),
                      [public_ack(kind, detail) for kind, _seq, detail in self.acks.sent])
        larger = self.entry(2, weight=0.65, signal_time=T0 + timedelta(minutes=5),
                            emitted=self.clock.now)
        self.executor.on_signal(larger)
        self.settle()
        self.assertEqual(self.broker.held(), {"MNQ": 1})

    def test_two_unit_base_trades_one_mnq_at_weight_point_four(self) -> None:
        self.broker.net_liq = 30_000.0  # 90,000 / 42,000 -> base 2
        self.executor.on_signal(self.entry(weight=0.4))
        self.settle()
        self.assertEqual(self.broker.held(), {"MNQ": 1})

    def test_per_order_quantity_limit_refuses_the_book(self) -> None:
        self.broker.net_liq = 2_000_000.0
        signal = self.entry()
        self.executor.on_signal(signal)
        self.settle()
        self.assertEqual(self.journal.trade_status(signal.trade_key), "refused")
        self.assertIn("exceeds risk.max_quantity 10", self.journal.recent("trades", 1)[0]["reason"])
        self.assertEqual(self.broker.placed("entry"), [])

    def test_margin_is_checked_for_the_whole_book_before_either_order(self) -> None:
        # Each order alone is below 50% of equity; together they are not.
        self.broker.margins = {"NQ": MarginEstimate(40_000.0, 100_000.0, "", 0.0),
                               "MNQ": MarginEstimate(52_000.0, 100_000.0, "", 40_000.0)}
        # The executor combines NQ 40,000 with MNQ's 52,000 - 40,000 = 12,000 increment.
        signal = self.entry()
        self.executor.on_signal(signal)
        self.settle()
        self.assertEqual(self.journal.trade_status(signal.trade_key), "refused")
        self.assertEqual(self.broker.placed("entry"), [])
        self.assertIn("52,000 exceeds 50%", self.journal.recent("trades", 1)[0]["reason"])
        self.assertEqual(sorted(r.contract.root for k, r in self.broker.calls if k == "what_if"),
                         ["MNQ", "NQ"])

    def test_margin_without_before_figures_is_conservative(self) -> None:
        self.broker.margins = {"NQ": MarginEstimate(30_000.0, 100_000.0),
                               "MNQ": MarginEstimate(21_000.0, 100_000.0)}
        signal = self.entry()
        self.executor.on_signal(signal)
        self.settle()
        self.assertEqual(self.journal.trade_status(signal.trade_key), "refused")

    def test_stop_risk_is_checked_for_the_whole_book(self) -> None:
        self.make(risk__max_stop_risk_usd=5_000)
        signal = self.entry(atr=10.0, stop_atr=10.0)  # (20 + 7 x 2) x 100 = 3,400
        self.executor.on_signal(signal)
        self.settle()
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 7})
        self.make(risk__max_stop_risk_usd=3_000)
        second = self.entry(2, signal_time=T0 + timedelta(minutes=5), emitted=self.clock.now,
                            atr=10.0, stop_atr=10.0)
        self.executor.on_signal(target(2, "exit", "flat"))
        self.settle(10)
        self.executor.on_signal(replace_seq(second, 3))
        self.settle()
        self.assertIn("stop risk $3,400", self.journal.recent("trades", 1)[0]["reason"])

    def test_held_book_never_resizes_on_continuation(self) -> None:
        self.executor.on_signal(self.entry(weight=0.62))  # 17 x 0.62 = 10.54 -> 1 NQ + 1 MNQ
        self.settle()
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 1})
        self.broker.net_liq = 1_000_000.0
        continued = target(2, "gap_drift_continuation", leg=LEG, stop=20900.0, reference=PRICE,
                           sizing=band(0.75), signal_time=T0 + timedelta(minutes=30),
                           emitted=self.clock.now)
        self.executor.on_signal(continued)
        self.settle()
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 1})
        self.assertEqual(len(self.broker.placed("entry")), 2)
        self.assertEqual(self.stops(), [("MNQ", 1, 20900.0), ("NQ", 1, 20900.0)])
        self.assertEqual(self.journal.trade_status(continued.trade_key), "entered")
        self.assertIsNone(self.journal.halt_reason())

    def test_flat_follower_sizes_a_continuation_as_a_new_entry(self) -> None:
        continued = target(2, "gap_drift_continuation", leg=LEG, stop=20900.0, reference=PRICE,
                           sizing=band(0.75))
        self.executor.on_signal(continued)
        self.settle()
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 3})  # 17 x 0.75 = 12.75 -> 13


class BookSafetyTests(BookTestCase):
    def test_both_roots_of_one_month_are_one_book_but_other_mixes_halt(self) -> None:
        self.executor.on_signal(self.entry())
        self.settle()
        self.assertIsNone(self.journal.halt_reason())
        other = contract("202703", "MNQ")
        self.broker.contracts[other.con_id] = other
        self.broker.positions[other.con_id] = 1
        self.settle()
        self.clock.advance(6)
        self.settle()
        self.assertTrue(self.journal.halt_reason().startswith("positions in more than one NQ/MNQ contract"))

    def test_nq_and_mnq_of_different_months_halt(self) -> None:
        nq, mnq = contract("202612", "NQ"), contract("202703", "MNQ")
        for item in (nq, mnq):
            self.broker.contracts[item.con_id] = item
            self.broker.positions[item.con_id] = 1
        self.settle()
        self.assertIn("more than one", self.journal.halt_reason())

    def test_restart_reconciles_both_contracts_without_duplicates(self) -> None:
        self.executor.on_signal(self.entry())
        self.settle()
        self.executor.on_signal(target(2, "protective_stop_installed", stop=20900.0, reference=PRICE,
                                       sizing=band()))
        self.settle()
        self.broker.connected = False
        self.restart()
        self.settle(10)
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 7})
        self.assertEqual(len(self.broker.placed("entry")), 2)
        self.assertEqual(len(self.broker.placed("stop")), 2)
        self.assertEqual(self.stops(), [("MNQ", 7, 20900.0), ("NQ", 1, 20900.0)])
        self.assertIsNone(self.journal.halt_reason())

    def test_unprotected_contract_is_closed_while_the_other_keeps_its_stop(self) -> None:
        self.broker.reject["stop"] = (201, "stop refused for this test")
        signal = self.entry()
        self.executor.on_signal(signal)
        self.executor.step()
        self.clock.advance(0.1)
        self.executor.step()
        self.clock.advance(0.1)
        self.settle(4)
        # One stop was refused, so the trade closes: the refused contract first,
        # while the other keeps its stop, then the remaining contract.
        self.clock.advance(31)
        self.settle(30)
        self.assertEqual(self.broker.held(), {})
        self.assertEqual(self.journal.trade_status(signal.trade_key), "closed")
        self.assertIsNone(self.journal.halt_reason())

    def test_emergency_exit_of_one_contract_keeps_the_other_stop_until_it_is_flat(self) -> None:
        signal = self.entry()
        self.executor.on_signal(signal)
        self.settle()
        nq_stop = next(o for o in self.broker.working("stop") if o.root == "NQ")
        mnq_stop = next(o for o in self.broker.working("stop") if o.root == "MNQ")
        self.executor._protection.force_close(nq_stop.con_id, self.clock.now, "entry protection timeout",
                                              signal.trade_key)
        self.settle(20)
        self.assertEqual(self.broker.held(), {})
        calls = self.broker.calls
        nq_exit = next(i for i, (kind, item) in enumerate(calls)
                       if kind == "place" and item.purpose == "exit" and item.contract.root == "NQ")
        self.assertLess(calls.index(("cancel", nq_stop.order_id)), nq_exit)
        # MNQ stays protected during the NQ emergency exit; the trade then closes it.
        self.assertGreater(calls.index(("cancel", mnq_stop.order_id)), nq_exit)
        self.assertEqual(self.journal.trade_status(signal.trade_key), "closed")

    def test_halted_executor_repairs_missing_stops_on_both_contracts(self) -> None:
        self.executor.on_signal(self.entry())
        self.settle()
        for order in self.broker.working("stop"):
            self.broker.cancel(order.order_id)
        self.journal.halt("test halt")
        self.settle()
        self.assertEqual([stop[:2] for stop in self.stops()], [("MNQ", 7), ("NQ", 1)])


class BookNotificationTests(BookTestCase):
    def test_each_contract_reports_its_own_root_and_profit(self) -> None:
        self.make(notifications__discord_link_id="a" * 32)
        notifications = Notifications(self.config, transport=lambda *_: {"accepted": True})
        self.addCleanup(notifications.close)
        notifications.observe(self.broker.state(), self.journal, self.clock.now)
        self.executor.on_signal(self.entry())
        self.settle()
        notifications.observe(self.broker.state(), self.journal, self.clock.now)
        self.broker.market = PRICE + 10
        self.executor.on_signal(target(2, "exit", "flat"))
        self.settle(10)
        notifications.observe(self.broker.state(), self.journal, self.clock.now)
        events = [json.loads(row["payload"]) for row in notifications.db.execute("SELECT payload FROM outbox")]
        positions = [(e["root"], e["position"], e["quantity"], e.get("gross_pnl")) for e in events
                     if e["kind"] == "position"]
        self.assertEqual(sorted(positions, key=str), sorted([
            ("NQ", "LONG", 1, None), ("MNQ", "LONG", 7, None),
            ("NQ", "FLAT", 1, 200.0), ("MNQ", "FLAT", 7, 140.0)], key=str))


def replace_seq(signal, seq):
    data = json.loads(signal.payload)
    data["seq"] = seq
    return parse_target(json.dumps(data, sort_keys=True, separators=(",", ":")), signal.stream)


if __name__ == "__main__":
    unittest.main()
