import unittest

import pandas as pd

from data_manager import DataManager


class TestHistoryDateNormalization(unittest.TestCase):
    def setUp(self):
        self.dm = DataManager.__new__(DataManager)

    def test_filters_invalid_date_rows_and_keeps_valid_rows(self):
        df = pd.DataFrame({
            "date": [
                "2026-06-12 15:00",
                "13598-74-57 15:00",
                "0-00-00 15:00",
                20260615,
                "20260616150000",
            ],
            "close": [1, 2, 3, 4, 5],
        })

        result = self.dm._normalize_history_dates(df, "999999.SH", source="unit")

        self.assertEqual(result["date"].tolist(), [
            "2026-06-12",
            "2026-06-15",
            "2026-06-16",
        ])
        self.assertEqual(result["close"].tolist(), [1, 4, 5])

    def test_renames_time_column_before_normalizing(self):
        df = pd.DataFrame({
            "time": ["20260612", "13598-74-57 15:00", "2026-06-15 15:00"],
            "close": [10, 20, 30],
        })

        result = self.dm._normalize_history_dates(df, "399001.SZ", source="unit")

        self.assertIn("date", result.columns)
        self.assertNotIn("time", result.columns)
        self.assertEqual(result["date"].tolist(), ["2026-06-12", "2026-06-15"])
        self.assertEqual(result["close"].tolist(), [10, 30])

    def test_normalizes_xtdata_epoch_millisecond_time(self):
        df = pd.DataFrame({
            "time": [1774972800000, 1775059200000],
            "close": [3948.552, 3919.285],
        })

        result = self.dm._normalize_history_dates(df, "000001.SH", source="unit")

        self.assertEqual(result["date"].tolist(), ["2026-04-01", "2026-04-02"])

    def test_adjusts_baostock_style_code_to_xt_code(self):
        self.assertEqual(self.dm._adjust_stock("sh.000001"), "000001.SH")
        self.assertEqual(self.dm._adjust_stock("sz.399001"), "399001.SZ")


if __name__ == "__main__":
    unittest.main()
