import os
import sys
import importlib
import types
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Methods


def _load_methods():
    """获取（必要时重载）Methods 模块，确保拿到最新模块对象。"""
    module_obj = sys.modules.get("Methods")
    if isinstance(module_obj, types.ModuleType):
        return importlib.reload(module_obj)
    sys.modules.pop("Methods", None)
    return importlib.import_module("Methods")


class _FakeLogin:
    def __init__(self, error_code='0', error_msg='success'):
        self.error_code = error_code
        self.error_msg = error_msg


class _FakeResult:
    def __init__(self, rows, fields, error_code='0', error_msg='success'):
        self._rows = list(rows)
        self.fields = list(fields)
        self.error_code = error_code
        self.error_msg = error_msg
        self._i = 0

    def next(self):
        return self._i < len(self._rows)

    def get_row_data(self):
        row = self._rows[self._i]
        self._i += 1
        return row


class _FakeBaostock:
    """模拟新版 baostock 模块（含 set_API_key 接口）。"""

    def __init__(self, login=None, query=None):
        self._login = login if login is not None else _FakeLogin()
        self._query = query
        self.api_key = None
        self.logged_out = False
        self.last_query = None

    def set_API_key(self, key):
        self.api_key = key

    def login(self):
        return self._login

    def logout(self):
        self.logged_out = True

    def query_history_k_data_plus(self, code, fields, start_date=None,
                                  end_date=None, frequency='d', adjustflag='3'):
        self.last_query = {
            'code': code, 'fields': fields, 'start_date': start_date,
            'end_date': end_date, 'frequency': frequency, 'adjustflag': adjustflag,
        }
        return self._query


class TestMethodsDataSource(unittest.TestCase):
    def test_daily_data_uses_mootdx_when_baostock_disabled(self):
        module_obj = sys.modules.get("Methods")
        if isinstance(module_obj, types.ModuleType):
            methods = importlib.reload(module_obj)
        else:
            sys.modules.pop("Methods", None)
            methods = importlib.import_module("Methods")
        mock_client = MagicMock()
        mock_df = pd.DataFrame({"datetime": ["2026-06-26"], "close": [10.0]})
        mock_client.bars.return_value = mock_df

        with patch.object(methods.config, "ENABLE_BAOSTOCK_HISTORY_DATA", False, create=True), \
             patch.object(methods.Quotes, "factory", return_value=mock_client) as mock_factory:
            result = methods.getStockData("600519", freq="d", offset=30, adjustflag="qfq")

        mock_factory.assert_called_once_with("std")
        mock_client.bars.assert_called_once_with(
            symbol="600519", frequency=9, offset=30, adjust="qfq"
        )
        self.assertIs(result, mock_df)

    def test_market_trend_uses_get_stock_data(self):
        module_obj = sys.modules.get("Methods")
        if isinstance(module_obj, types.ModuleType):
            methods = importlib.reload(module_obj)
        else:
            sys.modules.pop("Methods", None)
            methods = importlib.import_module("Methods")
        mock_df = pd.DataFrame({"close": [10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6]})

        with patch.object(methods.config, "ENABLE_BAOSTOCK_HISTORY_DATA", False, create=True), \
             patch.object(methods, "getStockData", return_value=mock_df) as mock_get_stock_data:
            self.assertTrue(methods.IsMarketGoingUp())

        mock_get_stock_data.assert_called_once()


class TestMethodsBaostockPath(unittest.TestCase):
    """验证新版 baostock(0.9.x) 收紧访问后的规范化行为。"""

    def test_baostock_enabled_builds_df_and_normalizes(self):
        methods = _load_methods()
        fake = _FakeBaostock(
            login=_FakeLogin('0'),
            query=_FakeResult(
                rows=[['2026-06-26', 'sh.600519', '100.0'],
                      ['2026-06-27', 'sh.600519', '101.0']],
                fields=['date', 'code', 'close'],
            ),
        )

        with patch.dict(sys.modules, {'baostock': fake}), \
             patch.object(methods.config, 'ENABLE_BAOSTOCK_HISTORY_DATA', True, create=True), \
             patch.object(methods.config, 'BAOSTOCK_API_KEY', 'k-1', create=True):
            df = methods.getStockData(
                '600519', fields='date,code,close',
                start_date='2026-06-01', end_date='2026-06-27',
                freq='d', adjustflag='qfq')

        self.assertEqual(list(df.columns), ['date', 'code', 'close'])
        self.assertEqual(len(df), 2)
        self.assertEqual(fake.api_key, 'k-1')                  # 登录前应用 API Key
        self.assertEqual(fake.last_query['code'], 'sh.600519')  # add_bs_prefix 规范化代码
        self.assertEqual(fake.last_query['adjustflag'], '2')   # qfq -> 2（复权归一化）
        self.assertEqual(fake.last_query['frequency'], 'd')
        self.assertTrue(fake.logged_out)                       # 确保 logout 释放连接

    def test_baostock_login_failure_falls_back_to_mootdx(self):
        methods = _load_methods()
        fake = _FakeBaostock(login=_FakeLogin('10001007', '需要激活'))
        mock_client = MagicMock()
        mock_df = pd.DataFrame({'close': [10.0]})
        mock_client.bars.return_value = mock_df

        with patch.dict(sys.modules, {'baostock': fake}), \
             patch.object(methods.config, 'ENABLE_BAOSTOCK_HISTORY_DATA', True, create=True), \
             patch.object(methods.Quotes, 'factory', return_value=mock_client) as mock_factory:
            result = methods.getStockData('600519', freq='d', offset=30, adjustflag='qfq')

        self.assertIs(result, mock_df)
        mock_factory.assert_called_once_with('std')
        mock_client.bars.assert_called_once_with(
            symbol='600519', frequency=9, offset=30, adjust='qfq')
        self.assertFalse(fake.logged_out)  # 登录失败无需 logout

    def test_baostock_not_installed_falls_back_to_mootdx(self):
        methods = _load_methods()
        mock_client = MagicMock()
        mock_df = pd.DataFrame({'close': [10.0]})
        mock_client.bars.return_value = mock_df

        with patch.dict(sys.modules, {'baostock': None}), \
             patch.object(methods.config, 'ENABLE_BAOSTOCK_HISTORY_DATA', True, create=True), \
             patch.object(methods.Quotes, 'factory', return_value=mock_client) as mock_factory:
            result = methods.getStockData('600519', freq='d', offset=30, adjustflag='qfq')

        self.assertIs(result, mock_df)
        mock_factory.assert_called_once_with('std')


if __name__ == "__main__":
    unittest.main()
