import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfigEnvOverrides(unittest.TestCase):
    def setUp(self):
        self._env_keys = [
            "GRID_REQUIRE_PROFIT_TRIGGERED",
            "ENABLE_BAOSTOCK_STOCK_NAME_LOOKUP",
            "ENABLE_BAOSTOCK_HISTORY_DATA",
        ]
        self._orig_env = {key: os.environ.get(key) for key in self._env_keys}

    def tearDown(self):
        for key, value in self._orig_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        if "config" in sys.modules:
            importlib.reload(sys.modules["config"])

    def _reload_config(self):
        if "config" in sys.modules:
            return importlib.reload(sys.modules["config"])

        import config
        return config

    def test_grid_require_profit_triggered_reads_env(self):
        os.environ["GRID_REQUIRE_PROFIT_TRIGGERED"] = "true"
        config = self._reload_config()
        self.assertTrue(config.GRID_REQUIRE_PROFIT_TRIGGERED)

        os.environ["GRID_REQUIRE_PROFIT_TRIGGERED"] = "0"
        config = self._reload_config()
        self.assertFalse(config.GRID_REQUIRE_PROFIT_TRIGGERED)

    def test_baostock_switches_default_to_disabled(self):
        os.environ.pop("ENABLE_BAOSTOCK_STOCK_NAME_LOOKUP", None)
        os.environ.pop("ENABLE_BAOSTOCK_HISTORY_DATA", None)

        config = self._reload_config()

        self.assertFalse(config.ENABLE_BAOSTOCK_STOCK_NAME_LOOKUP)
        self.assertFalse(config.ENABLE_BAOSTOCK_HISTORY_DATA)


if __name__ == "__main__":
    unittest.main()
