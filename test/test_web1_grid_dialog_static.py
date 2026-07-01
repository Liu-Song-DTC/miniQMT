#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""web1.0 网格配置弹窗静态回归测试。"""

import os
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB1_DIR = os.path.join(PROJECT_ROOT, "web1.0")


class TestWeb1GridDialogStatic(unittest.TestCase):
    def _read_web1_file(self, filename):
        with open(os.path.join(WEB1_DIR, filename), "r", encoding="utf-8") as f:
            return f.read()

    def test_grid_dialog_has_auto_toggle_and_deviation_placeholder(self):
        html = self._read_web1_file("index.html")

        self.assertIn('id="gridAutoToggleRow"', html)
        self.assertIn('id="gridAutoEnabled"', html)
        self.assertIn('id="gridAutoStatusLabel"', html)
        self.assertIn('id="gridCurrentPriceDeviation"', html)

    def test_grid_dialog_script_wires_enabled_api_and_deviation_calculation(self):
        script = self._read_web1_file("script.js")

        self.assertIn("/api/grid/session/${sessionId}/enabled", script)
        self.assertIn("function updateGridPriceDeviation", script)
        self.assertIn("function updateGridAutoToggleUI", script)
        self.assertIn("setGridSessionEnabled(activeSessionId", script)
        self.assertIn("centerPriceInput.addEventListener('input'", script)

    def test_top_auto_switches_are_split_and_wired(self):
        html = self._read_web1_file("index.html")
        script = self._read_web1_file("script.js")

        self.assertNotIn('id="globalAutoOperation"', html)
        self.assertNotIn('全局策略自动运行', html)
        self.assertIn('id="apiToken"', html)
        self.assertIn('id="simulationMode"', html)
        self.assertIn('允许自动止盈', html)
        self.assertIn('id="globalAllowGridTrading"', html)
        self.assertIn('允许自动网格', html)

        switch_order = [
            'id="apiToken"',
            'id="simulationMode"',
            'id="globalAllowBuySell"',
            'id="globalAllowGridTrading"',
        ]
        switch_positions = [html.index(marker) for marker in switch_order]
        self.assertEqual(switch_positions, sorted(switch_positions))
        self.assertIn("flex-nowrap", html)
        self.assertIn("overflow-x-auto", html)

        self.assertNotIn('setGlobalAutoOperation(event.target.checked)', script)
        self.assertNotIn('globalAutoOperation: elements.globalAutoOperation.checked', script)
        self.assertIn('globalAllowGridTrading: elements.globalAllowGridTrading.checked', script)
        self.assertIn('{ globalAllowGridTrading: gridTradingEnabled }', script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
