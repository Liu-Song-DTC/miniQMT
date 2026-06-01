"""
网格实盘委托成交确认与执行前复核测试

覆盖：
1. 实盘委托成功后不立即落账，等待成交回调确认
2. 部分成交按成交回报增量落账
3. 旧信号、会话错配、价格漂移过大时拒绝执行
4. 成交回调路径不依赖废弃的 GRID_TRADING_ENABLED
"""

import os
import sys
import sqlite3
import unittest
from dataclasses import asdict
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from grid_database import DatabaseManager
from grid_trading_manager import GridSession, GridTradingManager, PriceTracker
from position_manager import PositionManager
from trading_executor import TradingExecutor, DIRECTION_BUY


class FakeTrade:
    def __init__(self, order_id, stock_code='000001.SZ', volume=100, price=10.0, trade_id='DEAL_1'):
        self.order_id = order_id
        self.stock_code = stock_code
        self.traded_volume = volume
        self.traded_price = price
        self.trade_id = trade_id


class FakeDealInfo:
    m_strInstrumentID = '000001.SZ'
    m_nDirection = DIRECTION_BUY
    m_dPrice = 10.0
    m_nVolume = 100
    m_strTradeID = 'DEAL_OLD_SWITCH'
    m_dComssion = 0.0
    m_strOrderID = 'ORDER_OLD_SWITCH'


class TestGridLiveOrderConfirmation(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(':memory:')
        self.db.init_grid_tables()
        self.position_manager = Mock(spec=PositionManager)
        self.position_manager.signal_lock = __import__('threading').Lock()
        self.position_manager.latest_signals = {}
        self.position_manager._increment_data_version = Mock()
        self.position_manager.data_manager = Mock()
        self.position_manager.data_manager.get_latest_data.return_value = {'lastPrice': 10.0}
        self.executor = Mock(spec=TradingExecutor)
        self.manager = GridTradingManager(self.db, self.position_manager, self.executor)

        self.orig_sim = config.ENABLE_SIMULATION_MODE
        self.orig_confirm = getattr(config, 'GRID_CONFIRM_LIVE_ORDER_BY_DEAL', True)
        self.orig_max_age = getattr(config, 'GRID_SIGNAL_MAX_AGE_SECONDS', 60)
        self.orig_drift = getattr(config, 'GRID_SIGNAL_MAX_PRICE_DRIFT_RATIO', 0.01)

    def tearDown(self):
        config.ENABLE_SIMULATION_MODE = self.orig_sim
        config.GRID_CONFIRM_LIVE_ORDER_BY_DEAL = self.orig_confirm
        config.GRID_SIGNAL_MAX_AGE_SECONDS = self.orig_max_age
        config.GRID_SIGNAL_MAX_PRICE_DRIFT_RATIO = self.orig_drift
        self.db.close()

    def _make_session(self, stock_code='000001.SZ', current_investment=0.0):
        session = GridSession(
            id=None,
            stock_code=stock_code,
            status='active',
            center_price=10.0,
            current_center_price=10.0,
            price_interval=0.05,
            position_ratio=0.25,
            callback_ratio=0.005,
            max_investment=10000,
            current_investment=current_investment,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(days=7),
        )
        data = asdict(session)
        data['start_time'] = session.start_time.isoformat()
        data['end_time'] = session.end_time.isoformat()
        session.id = self.db.create_grid_session(data)
        self.manager.sessions[self.manager._normalize_code(stock_code)] = session
        self.manager.trackers[session.id] = PriceTracker(session_id=session.id, last_price=10.0)
        return session

    def _buy_signal(self, session, trigger_price=10.0):
        return {
            'stock_code': session.stock_code,
            'strategy': config.GRID_STRATEGY_NAME,
            'signal_type': 'BUY',
            'grid_level': 9.5,
            'trigger_price': trigger_price,
            'session_id': session.id,
            'timestamp': datetime.now().isoformat(),
            'signal_source': 'grid_tracker',
            'require_price_recheck': True,
            'valley_price': 9.9,
            'callback_ratio': 0.005,
        }

    def test_live_order_waits_for_deal_and_partial_fills_incrementally(self):
        config.ENABLE_SIMULATION_MODE = False
        config.GRID_CONFIRM_LIVE_ORDER_BY_DEAL = True
        session = self._make_session()
        signal = self._buy_signal(session)
        self.executor.buy_stock.return_value = {'order_id': 'ORDER_PARTIAL'}

        result = self.manager.execute_grid_trade(signal)

        self.assertTrue(result)
        self.assertIn('ORDER_PARTIAL', self.manager.pending_grid_orders)
        self.assertEqual(session.buy_count, 0)
        self.assertEqual(len(self.db.get_grid_trades(session.id)), 0)

        self.assertTrue(self.manager.handle_deal_callback(
            FakeTrade('ORDER_PARTIAL', volume=100, price=10.0, trade_id='DEAL_1')
        ))
        self.assertIn('ORDER_PARTIAL', self.manager.pending_grid_orders)
        self.assertEqual(session.buy_count, 1)
        self.assertEqual(session.total_buy_volume, 100)
        self.assertAlmostEqual(session.current_investment, 1000.0, places=2)

        self.assertTrue(self.manager.handle_deal_callback(
            FakeTrade('ORDER_PARTIAL', volume=100, price=10.1, trade_id='DEAL_2')
        ))
        self.assertNotIn('ORDER_PARTIAL', self.manager.pending_grid_orders)
        self.assertEqual(session.buy_count, 2)
        self.assertEqual(session.total_buy_volume, 200)
        self.assertAlmostEqual(session.current_investment, 2010.0, places=2)
        self.assertEqual(len(self.db.get_grid_trades(session.id, limit=10)), 2)

    def test_stale_signal_rejected_before_order(self):
        config.ENABLE_SIMULATION_MODE = False
        config.GRID_SIGNAL_MAX_AGE_SECONDS = 60
        session = self._make_session()
        signal = self._buy_signal(session)
        signal['timestamp'] = (datetime.now() - timedelta(seconds=120)).isoformat()

        result = self.manager.execute_grid_trade(signal)

        self.assertFalse(result)
        self.executor.buy_stock.assert_not_called()

    def test_session_mismatch_rejected_before_order(self):
        config.ENABLE_SIMULATION_MODE = False
        session = self._make_session()
        signal = self._buy_signal(session)
        signal['session_id'] = session.id + 999

        result = self.manager.execute_grid_trade(signal)

        self.assertFalse(result)
        self.executor.buy_stock.assert_not_called()

    def test_price_drift_rejected_before_order(self):
        config.ENABLE_SIMULATION_MODE = False
        config.GRID_SIGNAL_MAX_PRICE_DRIFT_RATIO = 0.01
        session = self._make_session()
        signal = self._buy_signal(session, trigger_price=10.0)
        self.position_manager.data_manager.get_latest_data.return_value = {'lastPrice': 10.25}

        result = self.manager.execute_grid_trade(signal)

        self.assertFalse(result)
        self.executor.buy_stock.assert_not_called()

    def test_trading_executor_deal_callback_without_old_grid_switch(self):
        executor = TradingExecutor.__new__(TradingExecutor)
        executor.position_manager = Mock()
        executor.position_manager.grid_manager = Mock()
        executor.order_cache = {}
        executor.callbacks = {}
        executor._save_trade_record = Mock()
        executor._update_position_after_trade = Mock()

        old_present = hasattr(config, 'GRID_TRADING_ENABLED')
        old_value = getattr(config, 'GRID_TRADING_ENABLED', None)
        if old_present:
            delattr(config, 'GRID_TRADING_ENABLED')
        try:
            self.assertFalse(hasattr(config, 'GRID_TRADING_ENABLED'))
            with patch.object(config, 'ENABLE_SIMULATION_MODE', False), \
                 patch.object(config, 'ENABLE_GRID_TRADING', True):
                executor._on_deal_callback(FakeDealInfo())
        finally:
            if old_present:
                setattr(config, 'GRID_TRADING_ENABLED', old_value)

        executor.position_manager.grid_manager.handle_deal_callback.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
