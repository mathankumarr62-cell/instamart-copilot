"""Unit tests for Part C: guardrails, redaction, validation, retries and routing (standard-library unittest only)."""
import random
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from instamart import io_utils  # noqa: E402
from instamart.llm_backend import TransientLLMError  # noqa: E402
from instamart.part_c import guardrails, llm_client, prompts, redaction, routing, validation  # noqa: E402
from instamart.part_c.pipeline import redaction_summary  # noqa: E402


class GuardrailTest(unittest.TestCase):
    def test_empty_and_whitespace_are_skipped(self):
        self.assertEqual(guardrails.check_input(""), "skipped_empty")
        self.assertEqual(guardrails.check_input("  \n\t "), "skipped_empty")

    def test_long_threshold_is_strictly_greater_than_400_tokens(self):
        self.assertIsNone(guardrails.check_input("word " * 307))           # ceil(307 * 1.3) = 400
        self.assertEqual(guardrails.check_input("word " * 308), "flagged_long")   # 401


class RedactionTest(unittest.TestCase):
    def test_each_type_and_order(self):
        text, counts = redaction.redact("Mail a.b+c@mail.co.in or 9876543210 about ORD-123456, not 5876543210.")
        self.assertEqual(text, "Mail [EMAIL] or [PHONE] about [ORDER_ID], not 5876543210.")
        self.assertEqual(counts, {"email": 1, "phone": 1, "order_id": 1})

    def test_reference_counts_on_all_tickets(self):
        summary = redaction_summary(io_utils.read_raw_tickets())
        self.assertEqual((summary["email"], summary["phone"], summary["order_id"], summary["total"]),
                         (55, 91, 132, 278))
        self.assertEqual(summary["left_after_redaction"], 0)

    def test_assertion_blocks_pii(self):
        with self.assertRaises(AssertionError):
            redaction.assert_no_pii([{"role": "user", "content": "call 9876543210"}])
        redaction.assert_no_pii([{"role": "user", "content": "call [PHONE]"}])


class ValidationTest(unittest.TestCase):
    def test_valid_json(self):
        self.assertEqual(validation.validate_reply('{"category": "fraud", "reason": "x"}'),
                         ("classified_json", "fraud"))

    def test_json_with_unknown_category_is_flagged(self):
        self.assertEqual(validation.validate_reply('{"category": "shipping", "reason": "x"}'),
                         ("flagged_invalid_output", ""))

    def test_hyphenated_keyword_reply(self):
        self.assertEqual(validation.validate_reply("The customer appears to have a billing-related problem."),
                         ("classified_keyword", "billing"))

    def test_two_category_words_or_none_are_flagged(self):
        self.assertEqual(validation.validate_reply("billing or delivery?")[0], "flagged_invalid_output")
        self.assertEqual(validation.validate_reply("no idea")[0], "flagged_invalid_output")
        self.assertEqual(validation.validate_reply("")[0], "flagged_invalid_output")


class PromptTest(unittest.TestCase):
    def test_prompt_contract(self):
        self.assertNotIn("EXAMPLES:", prompts.ZERO_SHOT)
        self.assertIn("\nEXAMPLES:\n", prompts.FEW_SHOT)
        for p in (prompts.ZERO_SHOT, prompts.FEW_SHOT):
            self.assertIn("CLASSIFY", p)
            self.assertIn('{"category": "...", "reason": "..."}', p)


class RetryTest(unittest.TestCase):
    def test_wait_range_for_retry_zero(self):
        rng = random.Random(0)
        waits = [llm_client.backoff_wait(0, rng) for _ in range(500)]
        self.assertTrue(all(0.045 <= w <= 0.0575 for w in waits))

    def test_gives_up_after_three_retries(self):
        log = llm_client.RetryLog()
        with mock.patch.object(llm_client, "chat", side_effect=TransientLLMError("503")) as chat, \
                mock.patch.object(llm_client.time, "sleep"):
            with self.assertRaises(TransientLLMError):
                llm_client.call_with_retry([{"role": "user", "content": "x"}], "T1", random.Random(0), log)
        self.assertEqual(chat.call_count, 4)
        self.assertEqual([n for _, n, _ in log.entries], [0, 1, 2])


class RoutingTest(unittest.TestCase):
    def test_rules_in_order(self):
        self.assertEqual(routing.route("budget_exhausted", "", True), ("human_review", "NORMAL"))
        self.assertEqual(routing.route("classified_json", "fraud", True), ("security_team", "HIGH"))
        self.assertEqual(routing.route("classified_keyword", "billing", True), ("premium_desk", "HIGH"))
        self.assertEqual(routing.route("classified_json", "delivery", False), ("support_queue", "NORMAL"))


if __name__ == "__main__":
    unittest.main()
