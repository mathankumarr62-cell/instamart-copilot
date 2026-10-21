"""Part C reference checkpoints, recomputed from the output CSVs and part_c.json."""
import pandas as pd

from instamart import config, io_utils
from instamart.part_c import prompts, routing
from instamart.validation import Check

STATUS_REFERENCE = {"classified_json": 135, "classified_keyword": 12, "flagged_invalid_output": 9,
                    "skipped_empty": 4, "flagged_long": 4}


def _input_checks(report: dict) -> list[Check]:
    """Guardrails, redaction, prompts and retries."""
    guard, red, retries = report["guardrails"], report["redaction"], report["retries"]
    return [
        Check("empty tickets", 4, guard["empty"]),
        Check("long tickets", 4, guard["long"]),
        Check("long tickets estimate 734 tokens", [734] * 4, guard["long_ticket_tokens"]),
        Check("redacted emails", 55, red["email"]),
        Check("redacted phones", 91, red["phone"]),
        Check("redacted order ids", 132, red["order_id"]),
        Check("redacted total", 278, red["total"]),
        Check("PII left after redaction", 0, red["left_after_redaction"]),
        Check("both prompts contain CLASSIFY and the four categories", True,
              all("CLASSIFY" in p and all(c in p for c in config.CATEGORIES)
                  for p in (prompts.ZERO_SHOT, prompts.FEW_SHOT))),
        Check("zero-shot has no EXAMPLES:, few-shot has an EXAMPLES: line with a fraud example", True,
              "EXAMPLES:" not in prompts.ZERO_SHOT and "\nEXAMPLES:\n" in prompts.FEW_SHOT
              and '"fraud"' in prompts.FEW_SHOT.split("EXAMPLES:")[1]),
        Check("TransientLLMErrors per full run", 19, retries["count"]),
        Check("permanent errors", 0, retries["permanent_errors"]),
        Check("every retry is retry 0 with wait in [0.045, 0.0575]", True,
              retries["retry_numbers"] == [0] and all(0.045 <= e["wait"] <= 0.0575 for e in retries["log"])),
    ]


def _comparison_checks(report: dict) -> list[Check]:
    """Status counts and prompt accuracies."""
    zero, few = report["zero_shot"], report["few_shot"]
    conf = {row["true"]: row for row in report["zero_shot_confusion"]}
    return [
        Check("zero-shot status counts", STATUS_REFERENCE, zero["status_counts"]),
        Check("few-shot status counts", STATUS_REFERENCE, few["status_counts"]),
        Check("classified tickets", 147, zero["classified"]),
        Check("zero-shot correct", 126, zero["correct"]),
        Check("zero-shot accuracy %", 85.7, zero["accuracy_pct"], tol=0.5),
        Check("zero-shot fraud->billing errors", 11, conf["fraud"]["billing"]),
        Check("zero-shot technical->billing errors", 10, conf["technical"]["billing"]),
        Check("few-shot accuracy %", 100.0, few["accuracy_pct"], tol=0.5),
    ]


def _output_checks(report: dict) -> list[Check]:
    """Budget demo and final routed results, re-derived from the CSV files."""
    demo = pd.read_csv(config.TRIAGE_BUDGET_DEMO, keep_default_na=False)
    final = pd.read_csv(config.TRIAGE_RESULTS, keep_default_na=False)
    segments = routing.load_segments().set_index("customer_id")["is_premium"]
    expected = [routing.route(s, c, bool(segments.get(cid, False)))
                for s, c, cid in zip(final["status"], final["category"], final["customer_id"])]
    return [
        Check("budget demo has >= 1 budget_exhausted", True, int((demo["status"] == "budget_exhausted").sum()) >= 1),
        Check("budget demo exhausted count matches report", report["budget_demo"]["budget_exhausted"],
              int((demo["status"] == "budget_exhausted").sum())),
        Check("triage_results.csv rows", 164, len(final)),
        Check("triage_results.csv columns", config.TRIAGE_COLUMNS, list(final.columns)),
        Check("triage_results.csv status counts", STATUS_REFERENCE, final["status"].value_counts().to_dict()),
        Check("rows whose route/priority break the rules", 0,
              sum(e != a for e, a in zip(expected, zip(final["route"], final["priority"])))),
        Check("no budget_exhausted at TOKEN_BUDGET=100000", 0, int((final["status"] == "budget_exhausted").sum())),
    ]


def build_checks() -> list[Check]:
    """Return every Part C checkpoint."""
    report = io_utils.read_json(config.report_path("c"))
    return _input_checks(report) + _comparison_checks(report) + _output_checks(report)
