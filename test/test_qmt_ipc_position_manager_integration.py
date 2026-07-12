"""
PositionManager integration tests for the Big-QMT IPC fallback.

These tests do not touch the real C:\\QuantIPC directory. They use a temporary
IPC root to verify that miniQMT's main trading path can treat QmtIpcTrader as an
xttrader-compatible fallback object.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "qmt-trader"))

import config


try:
    import position_manager
except ModuleNotFoundError:
    # Some lightweight CI/local Python environments do not install the market
    # data stack needed by data_manager/easy_qmt_trader. Fall back to stubs only
    # for this isolated test process. In the normal regression environment the
    # real modules are used, avoiding sys.modules pollution for later tests.
    class _FakeDataManager:
        def __init__(self):
            self.conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS positions ("
                "stock_code TEXT PRIMARY KEY, stock_name TEXT, volume REAL, "
                "available REAL, cost_price REAL, base_cost_price REAL, open_date TEXT, "
                "profit_triggered INTEGER, highest_price REAL, stop_loss_price REAL, "
                "profit_breakout_triggered INTEGER, breakout_highest_price REAL)"
            )
            self.conn.commit()

    _fake_data_manager = _FakeDataManager()
    _data_manager_mod = types.ModuleType("data_manager")
    _data_manager_mod.get_data_manager = lambda: _fake_data_manager
    sys.modules["data_manager"] = _data_manager_mod

    _easy_mod = types.ModuleType("easy_qmt_trader")
    _easy_mod.easy_qmt_trader = object
    sys.modules["easy_qmt_trader"] = _easy_mod
    sys.modules.pop("position_manager", None)
    import position_manager
from qmt_ipc_trader import QmtIpcTrader


class _PmIpcBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ipc_pm_")
        self.account = "TEST_ACC_PM"
        self.ipc_root = os.path.join(self.tmp, self.account)
        os.makedirs(os.path.join(self.ipc_root, "orders", "done"), exist_ok=True)
        os.makedirs(os.path.join(self.ipc_root, "cancel"), exist_ok=True)
        os.makedirs(os.path.join(self.ipc_root, "status"), exist_ok=True)
        self.patchers = [
            patch.object(config, "QMT_IPC_ROOT", self.tmp, create=True),
            patch.object(config, "QMT_IPC_ORDER_TIMEOUT", 1, create=True),
            patch.object(config, "QMT_IPC_HEARTBEAT_MAX_AGE", 10, create=True),
            patch.object(config, "QMT_IPC_DEAL_POLL_INTERVAL", 0.05, create=True),
            patch.object(config, "ENABLE_QMT_IPC_FALLBACK", True, create=True),
            patch.object(config, "ENABLE_XTQUANT_MANAGER", False, create=True),
            patch.object(config, "QMT_PATH", "C:/QMT/userdata_mini", create=True),
            patch.object(
                config,
                "get_account_config",
                return_value={"account_id": self.account, "account_type": "STOCK"},
            ),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_heartbeat(self):
        with open(os.path.join(self.ipc_root, "status", "heartbeat.json"), "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "account_id": self.account}, f)

    def _write_done(self, order_id, status="pending", stock="000001.SZ"):
        rec = {
            "version": "1.0",
            "order_id": order_id,
            "status": status,
            "action": "buy",
            "stock_code": stock,
            "filled_price": 10.5 if status in ("filled", "partial") else 0,
            "filled_volume": 1000 if status in ("filled", "partial") else 0,
            "total_volume": 1000,
            "strategy": "pm_integration",
            "remark": "",
            "error": None,
        }
        with open(os.path.join(self.ipc_root, "orders", "done", "ord_%s.json" % order_id),
                  "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        return rec

    def _pm_stub(self, trader=None, connected=True):
        pm = object.__new__(position_manager.PositionManager)
        pm.qmt_trader = trader or QmtIpcTrader(account=self.account, account_type="STOCK")
        pm.qmt_connected = connected
        return pm


class TestQmtIpcFactory(_PmIpcBase):
    def test_create_qmt_trader_returns_ipc_when_fallback_enabled(self):
        trader = position_manager._create_qmt_trader()
        try:
            self.assertIsInstance(trader, QmtIpcTrader)
            self.assertEqual(trader.account, self.account)
            self.assertEqual(trader.ipc_base_root, self.tmp)
            self.assertEqual(trader.path, "C:/QMT/userdata_mini")
        finally:
            trader.stop()

    def test_position_manager_connects_ipc_and_registers_callbacks(self):
        self._write_heartbeat()
        with patch.object(config, "ENABLE_SIMULATION_MODE", False, create=True), \
             patch.object(config, "ENABLE_GRID_TRADING", False, create=True), \
             patch.object(position_manager.PositionManager, "start_sync_thread", return_value=None):
            pm = position_manager.PositionManager()
        try:
            self.assertIsInstance(pm.qmt_trader, QmtIpcTrader)
            self.assertTrue(pm.qmt_connected)
            self.assertGreaterEqual(len(pm.qmt_trader._trade_callbacks), 1)
            self.assertGreaterEqual(len(pm.qmt_trader._order_callbacks), 1)
            self.assertGreaterEqual(len(pm.qmt_trader._disconnect_callbacks), 1)
        finally:
            pm.qmt_trader.stop()


class TestPositionManagerIpcContracts(_PmIpcBase):
    def test_default_async_order_id_path_uses_ipc_self_mapping(self):
        trader = QmtIpcTrader(account=self.account, account_type="STOCK")
        pm = self._pm_stub(trader)
        returned_id = 12345678
        trader._register_order_id(returned_id)
        with patch.object(config, "USE_SYNC_ORDER_API", False, create=True):
            self.assertEqual(pm._get_real_order_id(returned_id), returned_id)

    def test_pending_order_fallback_reads_ipc_done_records(self):
        trader = QmtIpcTrader(account=self.account, account_type="STOCK")
        trader._ensure_dirs()
        self._write_done(111, status="pending", stock="000001.SZ")
        self._write_done(222, status="filled", stock="000002.SZ")
        pm = self._pm_stub(trader)
        self.assertTrue(pm._has_pending_orders_fallback("000001.SZ"))
        self.assertFalse(pm._has_pending_orders_fallback("000002.SZ"))

    def test_query_order_status_reads_fake_xt_trader(self):
        trader = QmtIpcTrader(account=self.account, account_type="STOCK")
        trader._ensure_dirs()
        self._write_done(333, status="filled", stock="000001.SZ")
        pm = self._pm_stub(trader)
        self.assertEqual(pm._query_order_status("000001.SZ", "333"), 56)

    def test_cancel_order_writes_ipc_cancel_file(self):
        trader = QmtIpcTrader(account=self.account, account_type="STOCK")
        trader._ensure_dirs()
        pm = self._pm_stub(trader)
        with patch.object(config, "MAX_CANCEL_RETRIES", 1, create=True), \
             patch.object(config, "CANCEL_RETRY_INTERVAL_SECONDS", 0, create=True):
            self.assertTrue(pm._cancel_order("000001.SZ", "444"))
        self.assertTrue(os.path.exists(os.path.join(self.ipc_root, "cancel", "cancel_444.json")))

    def test_cancel_terminal_order_returns_false(self):
        trader = QmtIpcTrader(account=self.account, account_type="STOCK")
        trader._ensure_dirs()
        self._write_done(555, status="filled", stock="000001.SZ")
        pm = self._pm_stub(trader)
        with patch.object(config, "MAX_CANCEL_RETRIES", 1, create=True), \
             patch.object(config, "CANCEL_RETRY_INTERVAL_SECONDS", 0, create=True):
            self.assertFalse(pm._cancel_order("000001.SZ", 555))


if __name__ == "__main__":
    unittest.main()
