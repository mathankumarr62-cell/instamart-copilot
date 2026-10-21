"""Unit tests for Part D: chunking, RAG prompt, refund tools and agent limits (standard-library unittest only)."""
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from instamart import config  # noqa: E402
from instamart.part_d import agent, chunking, rag, tools  # noqa: E402

S1 = "My order ORD-100048 reached me very late. I would like a refund."


class ChunkingTest(unittest.TestCase):
    def test_window_arithmetic(self):
        words = [str(i) for i in range(100)]
        chunks = chunking.chunk_words(words, 40, 10)
        self.assertEqual([c[0] for c in chunks], ["0", "30", "60"])      # 60 + 40 reaches the end -> stop
        self.assertEqual(chunks[-1][-1], "99")
        self.assertEqual(len(chunking.chunk_words(words[:40], 40, 10)), 1)
        self.assertEqual(len(chunking.chunk_words(words[:41], 40, 10)), 2)

    def test_reference_chunk_counts(self):
        counts = Counter(c["source"] for c in chunking.chunk_documents())
        self.assertEqual(sum(counts.values()), 15)
        self.assertEqual(dict(counts), {"delivery_policy.txt": 3, "escalation_policy.txt": 3,
                                        "payment_policy.txt": 3, "privacy_policy.txt": 2, "refund_policy.txt": 4})

    def test_zero_overlap_has_fewer_chunks(self):
        self.assertEqual(len(chunking.chunk_documents(0)), 13)


class RagTest(unittest.TestCase):
    def test_user_message_format(self):
        msg = rag.build_user_message("Q?", [{"source": "a.txt", "text": "one"}, {"source": "b.txt", "text": "two"}])
        self.assertEqual(msg, "CONTEXT:\n[a.txt]\none\n[b.txt]\ntwo\nQUESTION:\nQ?")


class RefundToolTest(unittest.TestCase):
    def test_45_minutes_is_not_late_46_is(self):
        self.assertEqual(tools.calculate_refund(200.0, 45), {"refund_inr": 0.0})
        self.assertEqual(tools.calculate_refund(200.0, 46), {"refund_inr": 200.0})

    def test_only_completed_orders_and_rounding(self):
        self.assertEqual(tools.calculate_refund(99.999, 60), {"refund_inr": 100.0})
        self.assertEqual(tools.calculate_refund(200.0, 60, status="cancelled"), {"refund_inr": 0.0})
        self.assertEqual(tools.calculate_refund(200.0, None), {"refund_inr": 0.0})

    def test_escalation_boundary(self):
        self.assertFalse(tools.requires_escalation(1000))
        self.assertTrue(tools.requires_escalation(1000.01))

    def test_issue_refund_refuses_above_1000_and_ledger_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            with mock.patch.object(tools, "LEDGER_PATH", ledger):
                self.assertEqual(tools.issue_refund("ORD-1", 1000), {"refund_inr": 1000.0})
                self.assertIn("error", tools.issue_refund("ORD-2", 1000.01))
                self.assertEqual(tools.escalate_to_human("ORD-2", 1000.01), {"refund_inr": 1000.01})
                lines = [json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(x["tool"], x["order_id"]) for x in lines],
                         [("issue_refund", "ORD-1"), ("escalate_to_human", "ORD-2")])
        self.assertTrue(all("timestamp" in x for x in lines))

    def test_get_order(self):
        self.assertEqual(tools.get_order("ORD-999999"), {"error": "order not found"})
        self.assertEqual(tools.get_order("ORD-100048")["order_amount"], 128.25)

    def test_unknown_tool_and_bad_arguments(self):
        self.assertIn("error", tools.execute_tool("drop_tables", {}))
        self.assertIn("error", tools.execute_tool("get_order", {"wrong": 1}))


class AgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(config, "STATE_DIR", Path(self.tmp.name)),
                        mock.patch.object(tools, "LEDGER_PATH", Path(self.tmp.name) / "ledger.jsonl")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_status_parsing(self):
        self.assertEqual(agent.status_of("REFUND: INR 128.25 issued."), "REFUND")
        self.assertEqual(agent.status_of("no colon"), "UNKNOWN")

    def test_s1_and_limits(self):
        result = agent.run_agent(S1, "S1")
        self.assertEqual((result["status"], result["refund_inr"], result["llm_calls"]), ("REFUND", 128.25, 5))
        self.assertEqual(agent.run_agent(S1, "S1", time_limit_seconds=0)["llm_calls"], 0)
        tok = agent.run_agent(S1, "S1", token_limit=200)
        self.assertEqual(tok["status"], "FALLBACK_TOKEN_LIMIT")
        self.assertNotIn("calculate_refund", tok["tools_executed"])      # requested tool was not run

    def test_crash_and_resume_runs_each_tool_once(self):
        with self.assertRaises(agent.SimulatedCrash):
            agent.run_agent(S1, "S1", run_id="r", crash_after_tools=2)
        result = agent.resume_agent("r")
        self.assertEqual(result["tools_executed"], ["get_order", "search_policy", "calculate_refund", "issue_refund"])
        self.assertEqual((result["status"], result["refund_inr"]), ("REFUND", 128.25))

    def test_message_shapes(self):
        with self.assertRaises(agent.SimulatedCrash):
            agent.run_agent(S1, "S1", run_id="m", crash_after_tools=1)
        state = json.loads((Path(self.tmp.name) / "m.json").read_text(encoding="utf-8"))
        assistant, tool = state["messages"][2], state["messages"][3]
        self.assertEqual(set(assistant), {"role", "content", "tool_calls"})
        self.assertIsNone(assistant["content"])
        self.assertEqual(set(assistant["tool_calls"][0]), {"id", "name", "arguments"})
        self.assertEqual(set(tool), {"role", "tool_call_id", "name", "content"})
        self.assertIsInstance(json.loads(tool["content"]), dict)


if __name__ == "__main__":
    unittest.main()
