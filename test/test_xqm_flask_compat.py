"""
XtQuantManager Flask 兼容端点测试

验证 web2.0 前端通过网关访问时，/api/* 兼容端点返回的数据格式与
Flask web_server 一致（顶层字段 + 英文键），确保持仓/交易数据正确显示。

关键回归点（2026-05-25 修复）:
- 中文字段(证券代码/股票余额/市值...) → 英文字段(stock_code/volume/market_value...)
- 顶层字段对齐: connected/account/settings/ranges/data_version 不嵌套在 data 内
- X-Account-Id 请求头选择目标账号（多账号隔离）
- 委托类型 23→BUY / 24→SELL 映射
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from xtquant_manager.manager import XtQuantManager
from xtquant_manager.account import AccountConfig, XtQuantAccount
from xtquant_manager.server import create_app
from xtquant_manager.security import SecurityConfig
from test.test_xtquant_manager.mocks import (
    MockXtTrader, MockXtData, MockStockAccount, MockXtTrade,
)

ACC1 = "25105132"
ACC2 = "25106531"


def _inject_account(manager, account_id, positions=None, trades=None):
    cfg = AccountConfig(account_id=account_id, qmt_path="mock")
    acct = XtQuantAccount(cfg)
    trader = MockXtTrader()
    if positions:
        for p in positions:
            trader.add_mock_position(
                stock_code=p["stock_code"],
                volume=p["volume"],
                cost_price=p.get("cost_price", 10.0),
                current_price=p.get("current_price", 10.5),
            )
    if trades:
        for t in trades:
            trader._trades.append(MockXtTrade(
                account_type="STOCK", account_id=account_id,
                stock_code=t["stock_code"], order_type=t["order_type"],
                traded_id=t.get("traded_id", "T1"),
                traded_volume=t.get("traded_volume", 100),
                traded_price=t.get("traded_price", 10.0),
                traded_amount=t.get("traded_amount", 1000.0),
            ))
    acct._xt_trader = trader
    acct._acc = MockStockAccount(account_id)
    acct._xtdata = MockXtData()
    acct._connected = True
    acct._connected_at = time.time()
    acct._last_ping_ok_time = time.time()
    manager._accounts[account_id] = acct
    return acct


class TestFlaskCompatEndpoints(unittest.TestCase):
    def setUp(self):
        # 保存现有单例，避免污染其他在导入期建立状态的测试模块
        self._prev_instance = getattr(XtQuantManager, "_instance", None)
        XtQuantManager.reset_instance()
        self.manager = XtQuantManager.get_instance()
        _inject_account(self.manager, ACC1, positions=[
            {"stock_code": "000001.SZ", "volume": 1000, "cost_price": 10.0, "current_price": 10.5},
        ], trades=[
            {"stock_code": "000001.SZ", "order_type": 24, "traded_volume": 500, "traded_price": 10.5},
        ])
        _inject_account(self.manager, ACC2, positions=[
            {"stock_code": "600036.SH", "volume": 500, "cost_price": 35.0, "current_price": 36.0},
        ], trades=[
            {"stock_code": "600036.SH", "order_type": 23, "traded_volume": 200, "traded_price": 35.0},
        ])
        # TestClient host 为 "testclient"，需加入 local_ips 才能通过安全校验
        sec = SecurityConfig(api_token="", local_ips=["127.0.0.1", "::1", "localhost", "testclient", "unknown"])
        self.app = create_app(sec)
        self.client = TestClient(self.app)

    def tearDown(self):
        # 还原测试前的单例，保证跨模块运行时不破坏其他测试的状态
        XtQuantManager._instance = self._prev_instance

    # ---- /api/positions: 字段映射 + 顶层格式 ----

    def test_positions_status_at_top_level(self):
        r = self.client.get("/api/positions")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "success")
        self.assertIn("data", body)
        self.assertIn("data_version", body)  # 顶层字段
        self.assertIn("no_change", body)

    def test_positions_english_keys(self):
        r = self.client.get("/api/positions", headers={"X-Account-Id": ACC1})
        positions = r.json()["data"]["positions"]
        self.assertEqual(len(positions), 1)
        p = positions[0]
        # 英文键齐全
        for key in ("stock_code", "volume", "available", "cost_price",
                    "current_price", "market_value", "profit_ratio"):
            self.assertIn(key, p, f"缺少字段 {key}")
        self.assertEqual(p["stock_code"], "000001")
        self.assertEqual(p["volume"], 1000)
        self.assertEqual(p["cost_price"], 10.0)

    def test_positions_current_price_computed(self):
        """市价为 None 时应从 市值/股票余额 估算 = 10.5"""
        r = self.client.get("/api/positions", headers={"X-Account-Id": ACC1})
        p = r.json()["data"]["positions"][0]
        # market_value = 10.5 * 1000 = 10500; current = 10500/1000 = 10.5
        self.assertAlmostEqual(p["current_price"], 10.5, places=2)
        # profit_ratio = (10.5-10)/10 = 0.05
        self.assertAlmostEqual(p["profit_ratio"], 0.05, places=4)

    def test_positions_metrics_computed(self):
        r = self.client.get("/api/positions", headers={"X-Account-Id": ACC1})
        metrics = r.json()["data"]["metrics"]
        self.assertEqual(metrics["position_count"], 1)
        self.assertAlmostEqual(metrics["total_market_value"], 10500.0, places=1)

    # ---- X-Account-Id 账号隔离 ----

    def test_account_isolation_via_header(self):
        r1 = self.client.get("/api/positions", headers={"X-Account-Id": ACC1})
        r2 = self.client.get("/api/positions", headers={"X-Account-Id": ACC2})
        p1 = r1.json()["data"]["positions"][0]
        p2 = r2.json()["data"]["positions"][0]
        self.assertEqual(p1["stock_code"], "000001")
        self.assertEqual(p2["stock_code"], "600036")
        self.assertNotEqual(p1["stock_code"], p2["stock_code"])

    def test_no_header_falls_back_to_first_account(self):
        r = self.client.get("/api/positions")
        p = r.json()["data"]["positions"][0]
        # 无 header → 第一个注册账号 ACC1
        self.assertEqual(p["stock_code"], "000001")

    def test_invalid_account_id_falls_back(self):
        r = self.client.get("/api/positions", headers={"X-Account-Id": "9999999"})
        # 不存在的账号 → fallback 到第一个
        self.assertEqual(r.json()["status"], "success")
        self.assertEqual(len(r.json()["data"]["positions"]), 1)

    # ---- /api/status ----

    def test_status_top_level_fields(self):
        r = self.client.get("/api/status", headers={"X-Account-Id": ACC2})
        body = r.json()
        self.assertEqual(body["status"], "success")
        self.assertIn("account", body)        # 顶层
        self.assertIn("settings", body)        # 顶层
        self.assertIn("isMonitoring", body)
        self.assertEqual(body["account"]["id"], ACC2)
        self.assertIn("availableBalance", body["account"])

    # ---- /api/connection/status ----

    def test_connection_status_connected_top_level(self):
        r = self.client.get("/api/connection/status", headers={"X-Account-Id": ACC1})
        body = r.json()
        self.assertEqual(body["status"], "success")
        self.assertIn("connected", body)       # 顶层，不嵌套在 data
        self.assertTrue(body["connected"])

    # ---- /api/config ----

    def test_config_data_and_ranges_top_level(self):
        r = self.client.get("/api/config")
        body = r.json()
        self.assertEqual(body["status"], "success")
        self.assertIn("data", body)
        self.assertIn("ranges", body)          # 顶层
        self.assertIn("singleBuyAmount", body["data"])

    # ---- /api/trade-records: 数组 + BUY/SELL 映射 ----

    def test_trade_records_data_is_array(self):
        r = self.client.get("/api/trade-records", headers={"X-Account-Id": ACC1})
        body = r.json()
        self.assertEqual(body["status"], "success")
        self.assertIsInstance(body["data"], list)
        self.assertEqual(len(body["data"]), 1)

    def test_trade_records_sell_mapping(self):
        r = self.client.get("/api/trade-records", headers={"X-Account-Id": ACC1})
        t = r.json()["data"][0]
        self.assertEqual(t["trade_type"], "SELL")  # order_type 24 → SELL
        self.assertEqual(t["stock_code"], "000001")
        self.assertEqual(t["price"], 10.5)

    def test_trade_records_buy_mapping(self):
        r = self.client.get("/api/trade-records", headers={"X-Account-Id": ACC2})
        t = r.json()["data"][0]
        self.assertEqual(t["trade_type"], "BUY")   # order_type 23 → BUY
        self.assertEqual(t["stock_code"], "600036")

    def test_trade_records_english_keys(self):
        r = self.client.get("/api/trade-records", headers={"X-Account-Id": ACC1})
        t = r.json()["data"][0]
        for key in ("stock_code", "trade_type", "price", "volume", "trade_id"):
            self.assertIn(key, t, f"缺少字段 {key}")

    # ---- /api/positions-all ----

    def test_positions_all_data_is_array(self):
        r = self.client.get("/api/positions-all", headers={"X-Account-Id": ACC1})
        body = r.json()
        self.assertEqual(body["status"], "success")
        self.assertIsInstance(body["data"], list)
        self.assertEqual(body["data"][0]["stock_code"], "000001")


if __name__ == "__main__":
    unittest.main(verbosity=2)
