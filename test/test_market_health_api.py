import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


class TestMarketHealthApi(unittest.TestCase):
    def test_market_health_api_returns_memory_snapshot(self):
        import web_server

        fake_snapshot = {
            "enabled": True,
            "observe_only": True,
            "overall": {"score": 90, "status": "healthy"},
            "sources": {"xtdata": {"score": 90, "status": "healthy"}},
            "stocks": {},
        }

        fake_data_manager = SimpleNamespace(
            get_market_health_snapshot=Mock(return_value=fake_snapshot),
            get_latest_data=Mock(),
        )

        with patch.object(web_server, "data_manager", fake_data_manager):
            client = web_server.app.test_client()
            response = client.get("/api/market/health")

        fake_data_manager.get_market_health_snapshot.assert_called_once_with()
        fake_data_manager.get_latest_data.assert_not_called()
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["overall"]["status"], "healthy")
        self.assertEqual(payload["data"]["sources"]["xtdata"]["score"], 90)


if __name__ == "__main__":
    unittest.main()
