"""Part D reference checkpoints, recomputed from part_d.json, the JSONL logs and state/."""
import json

from instamart import config, io_utils
from instamart.part_d import checkpoint
from instamart.part_d.retrieval import retrieve
from instamart.validation import Check, money

CHUNK_REFERENCE = {"refund_policy.txt": 4, "delivery_policy.txt": 3, "escalation_policy.txt": 3,
                   "payment_policy.txt": 3, "privacy_policy.txt": 2}
S1_TOOLS = ["get_order", "search_policy", "calculate_refund", "issue_refund"]
S1_CALLS = 5


def _rag_checks(report: dict) -> list[Check]:
    """Chunks, retrieval and the two evaluation runs."""
    ev10, ev0 = report["evaluation"]["overlap_10"], report["evaluation"]["overlap_0"]
    return [
        Check("chunks total", 15, report["chunks"]["total"]),
        Check("chunks per source", CHUNK_REFERENCE, report["chunks"]["per_source"]),
        Check("'refund policy late delivery' top-3 all refund_policy.txt", ["refund_policy.txt"] * 3,
              [r["source"] for r in retrieve("refund policy late delivery")]),
        Check("overlap 10: expected_doc in top 3", 12, ev10["doc_in_top3"]),
        Check("overlap 10: expected_fact in answer", 12, ev10["fact_in_answer"]),
        Check("overlap 10: fallback on unanswerable", 2, ev10["fallback_on_unanswerable"]),
        Check("overlap 0: at least one answerable question fails", True,
              any(f["answerable"] for f in ev0["failures"])),
    ]


def _scenario_checks(report: dict, runs: list[dict]) -> list[Check]:
    """Each scenario's outcome and refund, S1 call count and S7 within the default token limit."""
    out = []
    for row in report["scenarios"]:
        expected = row["expected_outcome"]
        status_ok = row["status"] == expected or (expected == "FALLBACK" and row["status"].startswith("FALLBACK_"))
        out.append(Check(f"{row['scenario_id']} outcome {expected}", True, status_ok))
        out.append(Check(f"{row['scenario_id']} refund INR", row["expected_refund_inr"], money(row["refund_inr"]),
                         tol=0.01))
    by_id = {r["scenario_id"]: r for r in report["scenarios"]}
    s7 = by_id["S7"]
    scenario_runs = [r for r in runs if r["run_type"] == "scenario"]
    out += [
        Check("S1 model calls", S1_CALLS, by_id["S1"]["llm_calls"]),
        Check("S7 status", "FALLBACK_MAX_ITERATIONS", s7["status"]),
        Check("S7 made all 6 model calls under token_limit 6000", True,
              s7["llm_calls"] == 6 and s7["tokens_used"] <= config.AGENT_TOKEN_LIMIT),
        Check("agent_runs.jsonl has one scenario line per scenario", [f"S{i}" for i in range(1, 8)],
              [r["scenario_id"] for r in scenario_runs]),
        Check("every agent_runs.jsonl line has the required fields", True,
              all({"scenario_id", "status", "final_answer", "llm_calls", "tokens_used", "steps"} <= r.keys()
                  and all({"tool", "arguments", "observation"} <= s.keys() for s in r["steps"]) for r in runs)),
    ]
    return out


def _demo_checks(report: dict, runs: list[dict], ledger: list[dict]) -> list[Check]:
    """Stop-safely demos, crash-and-resume and the ledger."""
    demos = report["demos"]
    resume = demos["crash_resume"]
    resume_run = next(r for r in runs if r["run_type"] == "crash_resume")
    scenario_ledger = [(e["tool"], e["order_id"], e["refund_inr"]) for e in ledger if e["run_id"] in ("S1", "S2", "S3")]
    return [
        Check("S1 with token_limit=200", "FALLBACK_TOKEN_LIMIT", demos["token_limit_200"]["status"]),
        Check("time_limit_seconds=0", "FALLBACK_TIMEOUT", demos["time_limit_0"]["status"]),
        Check("time_limit_seconds=0 makes no model call", 0, demos["time_limit_0"]["llm_calls"]),
        Check("crash happened after 2 tools", S1_TOOLS[:2], resume["tools_before_crash"]),
        Check("crash+resume tools executed", S1_TOOLS, [s["tool"] for s in resume_run["steps"]]),
        Check("crash+resume final status and refund", ("REFUND", 128.25), (resume["status"], money(resume["refund_inr"]))),
        Check("crash+resume checkpoint saved in state/", S1_TOOLS,
              checkpoint.load(resume["run_id"])["tools_executed"]),
        Check("refund_ledger.jsonl actions for S1-S3", [("issue_refund", "ORD-100048", 128.25),
                                                        ("issue_refund", "ORD-100067", 135.0),
                                                        ("escalate_to_human", "ORD-100145", 1999.0)], scenario_ledger),
        Check("every ledger line has timestamp, tool, order_id, refund_inr", True,
              all({"timestamp", "tool", "order_id", "refund_inr"} <= e.keys() for e in ledger)),
    ]


def _read_jsonl(path) -> list[dict]:
    """Read a JSON-lines file."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_checks() -> list[Check]:
    """Return every Part D checkpoint."""
    report = io_utils.read_json(config.report_path("d"))
    runs, ledger = _read_jsonl(config.AGENT_RUNS), _read_jsonl(config.REFUND_LEDGER)
    return _rag_checks(report) + _scenario_checks(report, runs) + _demo_checks(report, runs, ledger)
