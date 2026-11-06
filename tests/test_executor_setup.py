# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from executor_support import T0, FakeBroker, Leader, target, write_config

from follow_executor.cli import main
from follow_executor.config import ConfigError, load_config
from follow_executor.executor import Executor
from follow_executor.journal import Journal
from follow_executor.local import bind_settings, exclusive, settings_identity
from follow_executor.setup import require_flat


class SetupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / 'config' / 'executor.json'
        self.env = patch.dict(os.environ, {'XDG_STATE_HOME': str(self.root / 'state')})
        self.env.start()
        self.addCleanup(self.env.stop)

    def call(self, command, *args, answers=()):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), \
             patch('builtins.input', side_effect=answers), \
             patch('getpass.getpass', return_value='secret-test-token'):
            code = main([command, '--config', str(self.path), *args])
        return code, output.getvalue()

    def configured(self):
        code, output = self.call('configure', answers=['paper', 'DU1234567', 'MNQ', '2'])
        self.assertEqual(code, 0, output)
        return load_config(self.path)

    def test_paper_setup_is_private_and_does_not_connect_or_trade(self):
        with patch('follow_executor.ibkr.IBKRBroker') as broker:
            code, output = self.call('configure', answers=['', 'DU1234567', 'MNQ', ''])
        self.assertEqual(code, 0, output)
        broker.assert_not_called()
        config = load_config(self.path)
        self.assertEqual((config.root, config.quantity, config.ibkr.port), ('MNQ', 1, 4002))
        self.assertEqual(config.token(), 'secret-test-token')
        self.assertNotIn('secret-test-token', output)
        for path in (self.path, config.token_path, config.journal_path):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_live_requires_confirmation_and_uses_live_port(self):
        code, _ = self.call('configure', answers=['live', 'U1234567', 'NQ', '1', 'no'])
        self.assertEqual(code, 2)
        self.assertFalse(self.path.exists())
        code, output = self.call('configure', answers=['live', 'U1234567', 'NQ', '1', 'LIVE U1234567'])
        self.assertEqual(code, 0, output)
        self.assertEqual(load_config(self.path).ibkr.port, 4001)

    def test_invalid_quantity_reprompts(self):
        code, output = self.call('configure', answers=['paper', 'DU1234567', 'MNQ', '0', 'two', '3'])
        self.assertEqual(code, 0, output)
        self.assertEqual(load_config(self.path).quantity, 3)

    def test_settings_checks_both_roots_and_preserves_trade_history(self):
        config = self.configured()
        journal = Journal(config.journal_path)
        journal.mark_trade('already-finished', 'closed', 'test')
        journal.close()
        with patch('follow_executor.setup.require_flat') as flat:
            code, output = self.call('settings', '--root', 'NQ', '--quantity', '1')
        self.assertEqual(code, 0, output)
        flat.assert_called_once_with(config, roots=('MNQ', 'NQ'))
        config = load_config(self.path)
        self.assertEqual((config.root, config.quantity), ('NQ', 1))
        journal = Journal(config.journal_path)
        self.addCleanup(journal.close)
        self.assertEqual(journal.trade_status('already-finished'), 'closed')
        bind_settings(journal, config)

    def test_reconfigure_edits_only_instrument_and_size(self):
        old = self.configured()
        with patch('follow_executor.setup.require_flat'):
            code, output = self.call('configure', answers=['NQ', '3'])
        self.assertEqual(code, 0, output)
        new = load_config(self.path)
        self.assertEqual(new.ibkr, old.ibkr)
        self.assertEqual(new.token(), old.token())
        self.assertEqual((new.root, new.quantity), ('NQ', 3))

    def test_active_process_prevents_settings_changes(self):
        self.configured()
        before = self.path.read_bytes()
        with exclusive(self.path.with_suffix('.json.lock')):
            code, output = self.call('settings', '--quantity', '3')
        self.assertEqual(code, 2, output)
        self.assertIn('running', output)
        self.assertEqual(self.path.read_bytes(), before)

    def test_another_config_cannot_bypass_shared_journal_lock(self):
        config = self.configured()
        with exclusive(config.journal_path.with_suffix('.sqlite3.lock')):
            code, output = self.call('settings', '--quantity', '3')
        self.assertEqual(code, 2, output)

    def test_open_recorded_position_and_halt_refuse_changes(self):
        config = self.configured()
        before = self.path.read_bytes()
        journal = Journal(config.journal_path)
        self.addCleanup(journal.close)
        journal.set_baseline({123: 2})
        with patch('follow_executor.setup.require_flat') as flat:
            code, output = self.call('settings', '--quantity', '3')
            flat.assert_not_called()
        self.assertEqual(code, 2, output)
        journal.set_baseline({})
        journal.halt('test halt')
        code, output = self.call('settings', '--quantity', '3')
        self.assertEqual(code, 2, output)
        self.assertEqual(self.path.read_bytes(), before)

    def test_gateway_failure_or_open_position_preserves_configuration(self):
        self.configured()
        before = self.path.read_bytes()
        for error in (ConnectionError('offline'), ConfigError('held position')):
            with self.subTest(error=error), patch('follow_executor.setup.require_flat', side_effect=error):
                code, output = self.call('settings', '--quantity', '3')
            self.assertEqual(code, 2, output)
            self.assertEqual(self.path.read_bytes(), before)

    def test_quantity_limits_do_not_contact_broker(self):
        self.configured()
        for quantity in ('0', '-1', '11'):
            with patch('follow_executor.setup.require_flat') as flat:
                code, output = self.call('settings', '--quantity', quantity)
            self.assertEqual(code, 2, output)
            flat.assert_not_called()

    def test_manual_account_or_instrument_change_cannot_reuse_journal(self):
        config = self.configured()
        journal = Journal(config.journal_path)
        self.addCleanup(journal.close)
        for changed in (replace(config, quantity=3), replace(config, root='NQ'),
                        replace(config, ibkr=replace(config.ibkr, account='DU7654321'))):
            with self.assertRaises(ConfigError):
                bind_settings(journal, changed)

    def test_colocated_config_and_journal_do_not_deadlock(self):
        config = write_config(self.root, Leader().public_key)
        self.path = self.root / 'executor.json'
        with patch('follow_executor.setup.require_flat'):
            code, output = self.call('settings', '--quantity', str(config.quantity + 1))
        self.assertEqual(code, 0, output)


    def test_balance_setup_validates_the_fraction_and_previews_example_weights(self):
        code, output = self.call('configure', answers=[
            'paper', 'DU1234567', 'balance', '0', '1.5', 'half', '0.5', '250,000', '21000'])
        self.assertEqual(code, 0, output)
        config = load_config(self.path)
        self.assertEqual((config.sizing.mode, config.sizing.leverage_fraction), ('balance', 0.5))
        self.assertEqual(config.roots, ('NQ', 'MNQ'))
        self.assertNotIn('instrument', json.loads(self.path.read_text()))
        self.assertEqual(output.count('Enter a number above 0 and at most 1'), 3)
        for line in ('base: 17 MNQ units', 'weight 1    -> 1 NQ + 7 MNQ', 'weight 0.75 -> 1 NQ + 3 MNQ',
                     'weight 0.25 -> 4 MNQ'):
            self.assertIn(line, output)
        self.assertIn('Saved NQ + MNQ balance sizing at leverage fraction 0.5 in paper mode', output)

    def test_balance_is_the_default_and_the_preview_can_be_skipped(self):
        code, output = self.call('configure', answers=['', 'DU1234567', '', '1', ''])
        self.assertEqual(code, 0, output)
        self.assertEqual(load_config(self.path).sizing.leverage_fraction, 1.0)
        self.assertIn('Preview skipped', output)

    def test_settings_switch_between_fixed_and_balance_while_flat(self):
        old = self.configured()
        journal = Journal(old.journal_path)
        journal.mark_trade('already-finished', 'closed', 'test')
        journal.close()
        with patch('follow_executor.setup.require_flat', return_value=250_000.0) as flat:
            code, output = self.call('settings', '--leverage-fraction', '0.25')
        self.assertEqual(code, 0, output)
        flat.assert_called_once_with(old, roots=('MNQ', 'NQ'))
        config = load_config(self.path)
        self.assertEqual(config.sizing.leverage_fraction, 0.25)
        journal = Journal(config.journal_path)
        self.addCleanup(journal.close)
        bind_settings(journal, config)
        self.assertEqual(journal.trade_status('already-finished'), 'closed')
        with patch('follow_executor.setup.require_flat'):
            code, output = self.call('settings', '--quantity', '3')
        self.assertEqual(code, 2, output)
        self.assertIn('needs both --root and --quantity', output)
        with patch('follow_executor.setup.require_flat'):
            code, output = self.call('settings', '--root', 'MNQ', '--quantity', '1')
        self.assertEqual(code, 0, output)
        config = load_config(self.path)
        self.assertEqual((config.sizing, config.root, config.quantity), (None, 'MNQ', 1))

    def test_fixed_to_balance_uses_one_broker_connection_for_both_roots(self):
        config = self.configured()
        broker = Mock(managed_accounts=(config.ibkr.account,))
        broker.state.return_value = Mock(positions={}, orders={})
        broker.net_liquidation.return_value = 250_000.0
        with patch('follow_executor.ibkr.IBKRBroker', side_effect=[broker]) as factory:
            code, output = self.call('settings', '--leverage-fraction', '1')
        self.assertEqual(code, 0, output)
        factory.assert_called_once_with(config.ibkr, ('MNQ', 'NQ'))
        broker.connect.assert_called_once_with()
        broker.wait_for_snapshot.assert_called_once_with()
        broker.disconnect.assert_called_once_with()
        broker.place.assert_not_called()
        broker.cancel.assert_not_called()
        self.assertEqual(load_config(self.path).sizing.leverage_fraction, 1)

    def test_scope_changes_refuse_positions_orders_and_incomplete_snapshots_before_saving(self):
        self.configured()
        fixed = self.path.read_text()
        balance_raw = json.loads(fixed)
        balance_raw.pop('instrument')
        balance_raw['sizing'] = {'mode': 'balance', 'leverage_fraction': 1}
        balance = json.dumps(balance_raw)
        for original, args in [(fixed, ('--leverage-fraction', '1')),
                               (fixed, ('--root', 'NQ', '--quantity', '1')),
                               (balance, ('--root', 'MNQ', '--quantity', '1'))]:
            for failure in ('position_MNQ', 'position_NQ', 'order_MNQ', 'order_NQ', 'snapshot', 'account'):
                with self.subTest(original=original == fixed, args=args, failure=failure):
                    self.path.write_text(original)
                    config = load_config(self.path)
                    journal = Journal(config.journal_path)
                    journal.set_state('settings_identity', settings_identity(config))
                    journal.close()
                    broker = Mock(managed_accounts=(config.ibkr.account,))
                    broker.state.return_value = Mock(positions={}, orders={})
                    if failure.startswith('position_'):
                        broker.state.return_value.positions = {failure: 1}
                    elif failure.startswith('order_'):
                        broker.state.return_value.orders = {failure: Mock(working=True)}
                    elif failure == 'snapshot':
                        broker.wait_for_snapshot.side_effect = RuntimeError('incomplete snapshot')
                    else:
                        broker.managed_accounts = ()
                    with patch('follow_executor.ibkr.IBKRBroker', side_effect=[broker]) as factory:
                        code, output = self.call('settings', *args)
                    self.assertEqual(code, 2, output)
                    self.assertEqual(set(factory.call_args.args[1]), {'MNQ', 'NQ'})
                    self.assertEqual(self.path.read_text(), original)
                    journal = Journal(config.journal_path)
                    try:
                        self.assertEqual(journal.get_state('settings_identity'), settings_identity(config))
                    finally:
                        journal.close()
                    broker.disconnect.assert_called_once_with()
                    broker.place.assert_not_called()
                    broker.cancel.assert_not_called()

    def test_interactive_settings_asks_for_the_fraction_with_an_ibkr_balance_preview(self):
        self.configured()
        with patch('follow_executor.setup.require_flat', return_value=250_000.0):
            code, output = self.call('settings', answers=['balance', '2', '0.5', '21000'])
        self.assertEqual(code, 0, output)
        self.assertIn('IBKR NetLiquidation: $250,000.00', output)
        self.assertIn('1 NQ + 7 MNQ', output)
        self.assertEqual(load_config(self.path).sizing.leverage_fraction, 0.5)
        with patch('follow_executor.setup.require_flat', return_value=250_000.0):
            code, output = self.call('settings', answers=['', '', ''])
        self.assertEqual(code, 0, output)
        self.assertIn('Already configured for NQ + MNQ balance sizing at leverage fraction 0.5', output)

    def test_invalid_fraction_options_never_contact_the_broker(self):
        self.configured()
        for args in (('--leverage-fraction', '0'), ('--leverage-fraction', '1.2'),
                     ('--leverage-fraction', '0.5', '--root', 'NQ')):
            with self.subTest(args=args), patch('follow_executor.setup.require_flat') as flat, \
                    self.assertRaises(SystemExit):
                self.call('settings', *args)
            flat.assert_not_called()

    def test_require_flat_checks_both_book_roots_and_reports_net_liquidation(self):
        config = self.configured()
        raw = json.loads(self.path.read_text())
        raw.pop('instrument')
        raw['sizing'] = {'mode': 'balance', 'leverage_fraction': 0.5}
        self.path.write_text(json.dumps(raw))
        balance = load_config(self.path)
        broker = Mock(managed_accounts=(config.ibkr.account,))
        broker.state.return_value = Mock(positions={}, orders={})
        broker.net_liquidation.return_value = 123_456.0
        with patch('follow_executor.ibkr.IBKRBroker', return_value=broker) as factory:
            self.assertEqual(require_flat(balance), 123_456.0)
        self.assertEqual(factory.call_args.args[1], ('NQ', 'MNQ'))
        broker.net_liquidation.side_effect = RuntimeError('summary unavailable')
        with patch('follow_executor.ibkr.IBKRBroker', return_value=broker):
            self.assertIsNone(require_flat(balance))


class BrokerSnapshotTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config = write_config(Path(directory.name), Leader().public_key)

    def test_settings_refuse_positions_orders_wrong_login_and_incomplete_snapshot(self):
        broker = Mock()
        broker.managed_accounts = (self.config.ibkr.account,)
        broker.state.return_value.positions = {}
        broker.state.return_value.orders = {}
        with patch('follow_executor.ibkr.IBKRBroker', return_value=broker):
            require_flat(self.config)
            broker.wait_for_snapshot.assert_called_once()
            broker.state.return_value.positions = {123: 1}
            with self.assertRaises(ConfigError):
                require_flat(self.config)
            broker.state.return_value.positions = {}
            broker.state.return_value.orders = {1: Mock(working=True)}
            with self.assertRaises(ConfigError):
                require_flat(self.config)
            broker.state.return_value.orders = {}
            broker.wait_for_snapshot.side_effect = TimeoutError('incomplete')
            with self.assertRaises(TimeoutError):
                require_flat(self.config)
            broker.wait_for_snapshot.side_effect = None
            broker.managed_accounts = ('DU9999999',)
            with self.assertRaises(ConfigError):
                require_flat(self.config)
        self.assertEqual(broker.disconnect.call_count, 5)
        broker.place.assert_not_called()
        broker.cancel.assert_not_called()

    def test_snapshot_waits_for_all_end_callbacks_and_rejects_timeout(self):
        from follow_executor.ibkr import IBKRBroker, IBKRError

        broker = IBKRBroker(replace(self.config.ibkr, timeout_seconds=0.1), 'MNQ')
        with patch.object(broker._app, 'isConnected', return_value=True):
            broker._ready.set()
            broker._app.positionEnd()
            with self.assertRaisesRegex(IBKRError, 'complete'):
                broker.wait_for_snapshot()
            broker._app.openOrderEnd()
            with self.assertRaisesRegex(IBKRError, 'complete'):
                broker.wait_for_snapshot()
            broker._execution_request_id = 1000001
            broker._app.execDetailsEnd(1000000)  # A stale request cannot finish this reconciliation.
            self.assertFalse(broker._executions_end.is_set())
            started = time.monotonic()
            timer = threading.Timer(0.03, broker._app.execDetailsEnd, args=(1000001,))
            timer.start()
            broker.wait_for_snapshot()
            timer.join()
            self.assertGreaterEqual(time.monotonic() - started, 0.025)
            broker._ready.clear()
            with self.assertRaisesRegex(IBKRError, 'disconnected'):
                broker.wait_for_snapshot()

    def test_incomplete_startup_snapshot_cannot_submit_an_entry(self):
        broker = FakeBroker()
        journal = Journal(self.config.journal_path)
        self.addCleanup(journal.close)
        executor = Executor(self.config, broker=broker, journal=journal, clock=lambda: T0)
        executor.on_signal(target(1, "entry"))
        with patch.object(broker, "wait_for_snapshot", side_effect=TimeoutError("snapshot")):
            self.assertEqual(executor.step(), [])
            self.assertFalse(broker.is_connected)
            self.assertEqual(executor.step(), [])
        self.assertEqual(broker.placed("entry"), [])

    def test_nonfinite_risk_and_credential_urls_are_refused(self):
        root = self.config.token_path.parent
        for risk in (float('nan'), float('inf')):
            with self.assertRaises(ConfigError):
                write_config(root, Leader().public_key, risk__max_stop_risk_usd=risk)
        with self.assertRaises(ConfigError):
            write_config(root, Leader().public_key, relay_url='https://token:secret@example.com')


class AcknowledgementPrivacyTests(unittest.TestCase):
    def test_wire_acknowledgements_exclude_account_positions_and_margin_amounts(self):
        from follow_executor.executor import AckSender

        with tempfile.TemporaryDirectory() as directory:
            config = write_config(Path(directory), Leader().public_key)
            sender = AckSender(config, 'test-token')
            cases = (
                ('error', {'reason': 'account DU1234567 is not managed by this login'}),
                ('error', {'reason': 'broker position {2026121: 7} differs from record'}),
                ('refused', {'reason': 'initial margin after entry 1,234 exceeds 50% of equity 2,345'}),
                ('refused', {'reason': 'stop risk $4,321 exceeds max_stop_risk_usd $1,111'}),
                ('rejected', {'purpose': 'entry', 'code': 201, 'account': 'DU1234567', 'quantity': 7}),
                ('missed', {'reason': 'entry deadline passed'}),
            )
            for kind, detail in cases:
                sender.send(kind, 1, detail)
                body = sender._queue.get_nowait()
                encoded = json.dumps(body)
                for private in ('DU1234567', '2026121', '1,234', '2,345', '4,321', '1,111', 'quantity'):
                    self.assertNotIn(private, encoded)
                self.assertIn(body['kind'], ('error', 'rejected'))
