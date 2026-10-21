"""Tests for the optional dashboard server: JSON shapes, static safety, body limits and the demo sandbox
(standard-library unittest only; needs the outputs of generate_data.py and run_all.py)."""
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from instamart import config  # noqa: E402
from instamart.dashboard import live, server  # noqa: E402

S1 = "My order ORD-100048 reached me very late. I would like a refund."


@unittest.skipUnless(config.report_path("d").exists() and config.DB_PATH.exists(), "run generate_data.py and run_all.py first")
class DashboardServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(0)                  # free port on 127.0.0.1
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, method: str, path: str, body: str | None = None, headers: dict | None = None):
        """Send one raw request (paths are not normalised) and return (status, headers, decoded body)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        hdrs = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=body.encode("utf-8") if body is not None else None, headers={**hdrs, **(headers or {})})
        res = conn.getresponse()
        raw = res.read().decode("utf-8")
        conn.close()
        return res.status, res.headers, raw

    def get_json(self, path: str) -> dict:
        status, headers, raw = self.request("GET", path)
        self.assertEqual(status, 200, raw)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        return json.loads(raw)

    def test_binds_to_loopback_only(self):
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")

    def test_index_and_static_files(self):
        for path, ctype in (("/", "text/html"), ("/styles.css", "text/css"), ("/app.js", "text/javascript")):
            status, headers, raw = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(headers["Content-Type"].startswith(ctype))
            self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
            self.assertNotIn(chr(36), raw)                  # no currency sign anywhere

    def test_overview_shape(self):
        d = self.get_json("/api/overview")
        self.assertEqual(set(d), {"kpis", "checkpoints"})
        for key in ("clean_orders", "completed_revenue_inr", "customers", "segments", "lapse_rate_pct",
                    "tickets_triaged", "scenarios_passed"):
            self.assertIn(key, d["kpis"])
        cp = d["checkpoints"]
        self.assertTrue(cp["all_passed"])
        self.assertEqual(cp["passed"], cp["total"])
        self.assertEqual(set(cp["checks"][0]), {"part", "name", "expected", "actual", "tolerance", "status"})

    def test_part_endpoints_shape(self):
        expected = {"/api/part-a": {"audit", "cleaning_rules", "sql", "eda", "orders_clean"},
                    "/api/part-b": {"segments", "lapse", "retention_caveat"},
                    "/api/part-c": {"zero_shot", "few_shot", "zero_shot_confusion", "final", "triage_rows"},
                    "/api/part-d": {"chunks", "evaluation", "scenarios", "demos", "ledger_lines"}}
        for path, keys in expected.items():
            with self.subTest(path=path):
                self.assertLessEqual(keys, set(self.get_json(path)))
        sql = self.get_json("/api/part-a")["sql"]
        self.assertEqual(sorted(sql), [f"Q{i}" for i in range(1, 8)])
        self.assertLessEqual({"sql", "columns", "rows", "row_count", "technique"}, set(sql["Q2"]))
        self.assertEqual(len(self.get_json("/api/part-c")["triage_rows"]), 164)
        self.assertEqual(len(self.get_json("/api/part-d")["scenarios"]), 7)

    def test_customer_lookup(self):
        c = self.get_json("/api/customers/C0060")
        self.assertEqual(c["segment"]["segment_name"], "Premium Big Spenders")
        self.assertAlmostEqual(c["lapse"]["lapse_probability"], 0.5025, places=4)   # matches retention_list.csv
        self.assertEqual(self.request("GET", "/api/customers/C9999")[0], 404)
        self.assertEqual(self.request("GET", "/api/customers/../../x")[0], 404)
        self.assertEqual(self.request("GET", "/api/customers/bad-id")[0], 400)

    def test_directory_traversal_is_blocked(self):
        for path in ("/../README.md", "/%2e%2e/README.md", "/..%2fREADME.md", "/..%5cREADME.md",
                     "/static/../../README.md", "/%00index.html", "/server.py", "/../app/server.py"):
            with self.subTest(path=path):
                status, headers, raw = self.request("GET", path)
                self.assertEqual(status, 404)
                self.assertIn("error", json.loads(raw))

    def test_oversized_and_invalid_bodies_are_rejected(self):
        too_long = json.dumps({"text": "a" * config.MAX_BODY_CHARS})
        self.assertEqual(self.request("POST", "/api/triage/try", too_long)[0], 413)
        self.assertEqual(self.request("POST", "/api/policy/ask", "[1, 2]")[0], 400)
        self.assertEqual(self.request("POST", "/api/policy/ask", "{bad")[0], 400)
        self.assertEqual(self.request("POST", "/api/policy/ask", json.dumps({"question": 5}))[0], 400)
        self.assertEqual(self.request("POST", "/api/policy/ask", '{"question": "x"}', {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/agent/run", json.dumps({"message": S1, "max_iterations": 99}))[0], 400)

    def test_methods_routes_and_host(self):
        self.assertEqual(self.request("DELETE", "/api/overview")[0], 405)
        self.assertEqual(self.request("GET", "/api/agent/run")[0], 405)
        self.assertEqual(self.request("POST", "/api/overview", "{}")[0], 405)
        self.assertEqual(self.request("GET", "/api/nope")[0], 404)
        self.assertEqual(self.request("GET", "/api/overview", headers={"Host": "evil.example"})[0], 400)

    def test_triage_try_redacts_and_routes(self):
        body = json.dumps({"text": "Charged twice for ORD-100048, call 9876543210", "customer_id": "C0060"})
        status, _, raw = self.request("POST", "/api/triage/try", body)
        self.assertEqual(status, 200, raw)
        r = json.loads(raw)
        self.assertEqual(r["redacted"], "Charged twice for [ORDER_ID], call [PHONE]")
        self.assertEqual(r["pii_left"], 0)
        self.assertEqual((r["route"], r["priority"]), ("premium_desk", "HIGH"))
        empty = json.loads(self.request("POST", "/api/triage/try", json.dumps({"text": "  "}))[2])
        self.assertEqual((empty["status"], empty["route"], empty["sent_to_model"]), ("skipped_empty", "human_review", False))

    def test_policy_ask_returns_scored_sources(self):
        status, _, raw = self.request("POST", "/api/policy/ask", json.dumps({"question": "refund policy late delivery"}))
        self.assertEqual(status, 200, raw)
        r = json.loads(raw)
        self.assertEqual([s["source"] for s in r["sources"]], ["refund_policy.txt"] * 3)
        self.assertAlmostEqual(r["sources"][0]["score"], 0.2719, places=4)

    def test_agent_demo_never_touches_graded_files(self):
        graded = {p: p.read_bytes() for p in (config.REFUND_LEDGER, config.AGENT_RUNS) if p.exists()}
        graded_state = sorted(p.name for p in config.STATE_DIR.glob("*.json"))
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            with mock.patch.object(config, "DEMO_DIR", demo), mock.patch.object(config, "DEMO_LEDGER", demo / "ledger.jsonl"), \
                    mock.patch.object(live, "DEMO_CHECKPOINTS", demo / "checkpoints"):
                first = json.loads(self.request("POST", "/api/agent/run", json.dumps({"message": S1, "customer_id": "C0007"}))[2])
                second = json.loads(self.request("POST", "/api/agent/run", json.dumps({"message": S1}))[2])
                self.assertEqual((first["status"], first["refund_inr"], first["llm_calls"]), ("REFUND", 128.25, 5))
                self.assertTrue(second["steps"][-1]["observation"]["duplicate_prevented"])
                self.assertEqual(len(first["steps"]), 4)
                self.assertEqual(len((demo / "ledger.jsonl").read_text(encoding="utf-8").splitlines()), 1)
                self.assertEqual(self.request("POST", "/api/agent/run", json.dumps({"message": S1, "token_limit": 200}))[0], 200)
        self.assertEqual({p: p.read_bytes() for p in graded}, graded)
        self.assertEqual(sorted(p.name for p in config.STATE_DIR.glob("*.json")), graded_state)


class StaticResolutionTest(unittest.TestCase):
    def test_resolve_static(self):
        self.assertEqual(server.resolve_static("/").name, "index.html")
        self.assertEqual(server.resolve_static("/app.js").name, "app.js")
        for bad in ("/../server.py", "/a/../../README.md", "/..\\x", "/missing.css", "//etc/passwd"):
            self.assertIsNone(server.resolve_static(bad), bad)


if __name__ == "__main__":
    unittest.main()
