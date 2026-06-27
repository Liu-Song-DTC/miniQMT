import os
import sys
import importlib
import types
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Methods


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


if __name__ == "__main__":
    unittest.main()
