import json
import threading
import unittest
from urllib.request import urlopen

from dashboard.server import StatePoller, create_dashboard_server


class DashboardHttpTests(unittest.TestCase):
    def setUp(self):
        self.sample = {
            "schema_version": 1,
            "status": "ok",
            "valid": True,
            "decision_ready": False,
            "observed_at_utc": "2026-09-24T02:00:00Z",
            "availability": {"sun_balance": "provisional", "cards.cost": "unavailable"},
            "sun_balance": 3333,
            "cards": [],
            "errors": [],
        }
        self.poller = StatePoller(50, sampler=lambda: self.sample)
        self.server = create_dashboard_server(self.poller, port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.poller.start()
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.poller.stop()
        self.thread.join(timeout=1)

    def test_state_endpoint_returns_shared_json_and_no_store(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/state") as response:
            record = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(record["sun_balance"], 3333)
        self.assertEqual(record["availability"]["cards.cost"], "unavailable")

    def test_page_and_static_resources_are_served_without_external_dependencies(self):
        with urlopen(f"http://127.0.0.1:{self.port}/") as response:
            page = response.read().decode("utf-8")
        with urlopen(f"http://127.0.0.1:{self.port}/static/app.js") as response:
            script = response.read().decode("utf-8")
        self.assertIn("草坪状态", page)
        self.assertIn("/static/style.css", page)
        self.assertIn("ZOMBIE_X_CALIBRATION = null", script)
        self.assertNotIn("fetch(\"http", script)

    def test_non_loopback_binding_is_rejected(self):
        with self.assertRaises(ValueError):
            create_dashboard_server(self.poller, host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
