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


if __name__ == "__main__":
    unittest.main(verbosity=2)
