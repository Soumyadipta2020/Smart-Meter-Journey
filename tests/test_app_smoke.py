import os
import unittest

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("ENABLE_AI_RECOMMENDATIONS", "false")
os.environ.setdefault("SMJ_AUTO_GENERATE_DATA", "false")

from app import app  # noqa: E402


class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def assert_json_response(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        self.assertTrue(response.is_json, path)
        payload = response.get_json()
        self.assertIsNotNone(payload, path)
        return payload

    def test_dashboard_page_renders(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Smart Meter", response.data)

    def test_health_reports_required_data_available(self):
        response = self.client.get("/api/health")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ok")
        missing = [
            filename
            for filename, health in payload["data_health"].items()
            if not health["exists"]
        ]
        self.assertEqual(missing, [])

    def test_region_reference_endpoint(self):
        payload = self.assert_json_response("/api/regions")
        codes = {region["code"] for region in payload}

        self.assertIn("NW", codes)
        self.assertIn("SE", codes)

    def test_core_dashboard_api_endpoints(self):
        endpoints = [
            "/api/journey/kpis?year=2025",
            "/api/forecasting/channel-kpis?year=2025",
            "/api/cancellations/kpis?year=2025",
            "/api/field-ops/kpis?year=2025",
            "/api/financial/kpis?year=2026",
            "/api/ai/recommendations?year=2025",
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                self.assert_json_response(endpoint)


if __name__ == "__main__":
    unittest.main()
