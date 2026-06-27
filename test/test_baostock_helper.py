import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import baostock_helper


class TestNormalizeAdjustflag(unittest.TestCase):
    def test_mootdx_style_mapped_to_baostock(self):
        self.assertEqual(baostock_helper.normalize_adjustflag('qfq'), '2')  # 前复权
        self.assertEqual(baostock_helper.normalize_adjustflag('hfq'), '1')  # 后复权
        self.assertEqual(baostock_helper.normalize_adjustflag('bfq'), '3')  # 不复权

    def test_numeric_strings_pass_through(self):
        self.assertEqual(baostock_helper.normalize_adjustflag('1'), '1')
        self.assertEqual(baostock_helper.normalize_adjustflag('2'), '2')
        self.assertEqual(baostock_helper.normalize_adjustflag('3'), '3')

    def test_case_insensitive_and_whitespace(self):
        self.assertEqual(baostock_helper.normalize_adjustflag(' QFQ '), '2')

    def test_none_and_unknown_default_to_no_adjust(self):
        self.assertEqual(baostock_helper.normalize_adjustflag(None), '3')
        self.assertEqual(baostock_helper.normalize_adjustflag(''), '3')
        self.assertEqual(baostock_helper.normalize_adjustflag('garbage'), '3')


class TestApplyApiKey(unittest.TestCase):
    def setUp(self):
        self._orig_key = getattr(config, 'BAOSTOCK_API_KEY', '')

    def tearDown(self):
        config.BAOSTOCK_API_KEY = self._orig_key

    def test_applies_when_key_configured_and_supported(self):
        config.BAOSTOCK_API_KEY = 'demo-key-123'
        bs = MagicMock()
        self.assertTrue(baostock_helper.apply_api_key(bs))
        bs.set_API_key.assert_called_once_with('demo-key-123')

    def test_skips_when_key_empty(self):
        config.BAOSTOCK_API_KEY = ''
        bs = MagicMock()
        self.assertFalse(baostock_helper.apply_api_key(bs))
        bs.set_API_key.assert_not_called()

    def test_skips_when_version_lacks_set_api_key(self):
        # 旧版 baostock(0.8.x) 没有 set_API_key 接口
        config.BAOSTOCK_API_KEY = 'demo-key-123'
        bs = MagicMock(spec=[])  # 无任何属性/方法
        self.assertFalse(baostock_helper.apply_api_key(bs))

    def test_returns_false_when_set_api_key_raises(self):
        config.BAOSTOCK_API_KEY = 'demo-key-123'
        bs = MagicMock()
        bs.set_API_key.side_effect = RuntimeError('boom')
        self.assertFalse(baostock_helper.apply_api_key(bs))


class TestDescribeLoginError(unittest.TestCase):
    def test_known_tightened_codes_get_hint(self):
        msg = baostock_helper.describe_login_error('10001007', '激活失败')
        self.assertIn('激活失败', msg)
        self.assertIn('激活', msg)

        # 权限不足提示包含 API Key 线索
        self.assertIn('BAOSTOCK_API_KEY', baostock_helper.describe_login_error('10001006'))

    def test_unknown_code_returns_original_msg(self):
        self.assertEqual(baostock_helper.describe_login_error('0', 'ok'), 'ok')
        self.assertEqual(baostock_helper.describe_login_error('99999999', 'weird'), 'weird')


if __name__ == '__main__':
    unittest.main()
