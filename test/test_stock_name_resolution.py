import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_manager import DataManager


class _FakeLogin:
    def __init__(self, error_code='0', error_msg='success'):
        self.error_code = error_code
        self.error_msg = error_msg


class _FakeBaostock:
    """模拟新版 baostock 模块（含 set_API_key 接口）。"""

    def __init__(self, login=None):
        self._login = login if login is not None else _FakeLogin()
        self.api_key = None

    def set_API_key(self, key):
        self.api_key = key

    def login(self):
        return self._login

    def logout(self):
        pass


class TestStockNameResolution(unittest.TestCase):
    def _make_manager(self, xt=None, cache=None):
        dm = object.__new__(DataManager)
        dm.xt = xt
        dm.stock_names_cache = dict(cache or {})
        dm._bs_consecutive_failures = 0
        dm._bs_cooldown_until = 0.0
        return dm

    def test_valid_cache_returns_without_external_lookup(self):
        xt = MagicMock()
        dm = self._make_manager(xt=xt, cache={'301577': '美信科技'})

        with patch('position_manager.get_position_manager') as mock_get_pm:
            self.assertEqual(dm.get_stock_name('301577'), '美信科技')

        mock_get_pm.assert_not_called()
        xt.get_instrument_detail.assert_not_called()

    def test_qmt_position_name_preferred_in_real_mode(self):
        xt = MagicMock()
        position_manager = MagicMock()
        position_manager.qmt_trader.position.return_value = pd.DataFrame([
            {'证券代码': '301577', '证券名称': '美信科技'}
        ])
        dm = self._make_manager(xt=xt)

        with patch('config.ENABLE_SIMULATION_MODE', False), \
             patch('position_manager.get_position_manager', return_value=position_manager):
            self.assertEqual(dm.get_stock_name('301577.SZ'), '美信科技')

        xt.get_instrument_detail.assert_not_called()
        self.assertEqual(dm.stock_names_cache['301577.SZ'], '美信科技')
        self.assertEqual(dm.stock_names_cache['301577'], '美信科技')

    def test_code_like_dirty_cache_is_replaced_by_xtdata_name(self):
        xt = MagicMock()
        xt.get_instrument_detail.side_effect = lambda code: (
            {'InstrumentName': '美信科技'} if code == '301577.SZ' else None
        )
        dm = self._make_manager(xt=xt, cache={'301577': '301577'})

        with patch('position_manager.get_position_manager', side_effect=RuntimeError('skip qmt')):
            self.assertEqual(dm.get_stock_name('301577'), '美信科技')

        self.assertEqual(dm.stock_names_cache['301577'], '美信科技')
        self.assertEqual(dm.stock_names_cache['301577.SZ'], '美信科技')

    def test_failed_lookup_does_not_cache_code_as_name(self):
        xt = MagicMock()
        xt.get_instrument_detail.return_value = None
        dm = self._make_manager(xt=xt)

        with patch('config.ENABLE_BAOSTOCK_STOCK_NAME_LOOKUP', True), \
             patch('position_manager.get_position_manager', side_effect=RuntimeError('skip qmt')), \
             patch('data_manager.DataManager._baostock_login_with_timeout', return_value=(None, 'timeout')):
            self.assertEqual(dm.get_stock_name('301577'), '301577')

        self.assertNotIn('301577', dm.stock_names_cache)

    def test_baostock_lookup_disabled_by_default(self):
        xt = MagicMock()
        xt.get_instrument_detail.return_value = None
        dm = self._make_manager(xt=xt)

        with patch('config.ENABLE_BAOSTOCK_STOCK_NAME_LOOKUP', False), \
             patch('position_manager.get_position_manager', side_effect=RuntimeError('skip qmt')), \
             patch('data_manager.DataManager._baostock_login_with_timeout') as mock_login:
            self.assertEqual(dm.get_stock_name('301577'), '301577')

        mock_login.assert_not_called()
        self.assertNotIn('301577', dm.stock_names_cache)

    def test_login_with_timeout_applies_api_key(self):
        """新版 baostock 收紧访问：登录前应通过 set_API_key 传入已配置的 API Key。"""
        dm = self._make_manager()
        fake_mod = _FakeBaostock(login=_FakeLogin('0'))

        with patch('config.BAOSTOCK_API_KEY', 'k-xyz'), \
             patch.dict(sys.modules, {'baostock': fake_mod}):
            lg, err = dm._baostock_login_with_timeout(timeout=3)

        self.assertIsNone(err)
        self.assertEqual(lg.error_code, '0')
        self.assertEqual(fake_mod.api_key, 'k-xyz')


if __name__ == '__main__':
    unittest.main()
