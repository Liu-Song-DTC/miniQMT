import unittest
from unittest.mock import patch


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

        with patch.object(web_server.data_manager, "get_market_health_snapshot", return_value=fake_snapshot):
            client = web_server.app.test_client()
            response = client.get("/api/market/health")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["overall"]["status"], "healthy")
        self.assertEqual(payload["data"]["sources"]["xtdata"]["score"], 90)


if __name__ == "__main__":
    unittest.main()
