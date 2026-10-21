"""Part D orchestration: chunking, retrieval, RAG evaluation, the seven agent scenarios, demos and resume."""
import json
import logging
from collections import Counter

import pandas as pd

from instamart import config, io_utils
from instamart.part_d import agent, checkpoint, evaluation
from instamart.part_d.chunking import chunk_documents
from instamart.part_d.retrieval import retrieve

log = logging.getLogger(__name__)

RETRIEVAL_EXAMPLE = "refund policy late delivery"


def reset_outputs() -> None:
    """Clear the ledger, the run log and old checkpoints so a full run is reproducible."""
    for path in (config.AGENT_RUNS, config.REFUND_LEDGER):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    checkpoint.clear_all()


def log_run(result: dict, run_type: str) -> None:
    """Append one JSON line per agent run to outputs/agent_runs.jsonl."""
    line = {"run_id": result["run_id"], "run_type": run_type, "scenario_id": result["scenario_id"],
            "status": result["status"], "final_answer": result["final_answer"], "refund_inr": result["refund_inr"],
            "llm_calls": result["llm_calls"], "tokens_used": result["tokens_used"],
            "steps": [{"tool": s["tool"], "arguments": s["arguments"], "observation": s["observation"]}
                      for s in result["steps"]]}
    with config.AGENT_RUNS.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line) + "\n")


def summary_row(result: dict) -> dict:
    """Compact per-run summary for the report and README."""
    return {k: result[k] for k in ("run_id", "scenario_id", "status", "refund_inr", "llm_calls", "tokens_used",
                                   "tools_executed")}


def run_scenarios(scenarios: pd.DataFrame) -> list[dict]:
    """Run all seven scenarios with default limits."""
    rows = []
    for s in scenarios.itertuples(index=False):
        result = agent.run_agent(s.message, s.scenario_id)
        log_run(result, "scenario")
        rows.append({**summary_row(result), "expected_outcome": s.expected_outcome,
                     "expected_refund_inr": float(s.expected_refund_inr)})
    return rows


def run_demos(s1_message: str) -> dict:
    """Token-limit and timeout fallbacks, then the S1 crash-and-resume demonstration."""
    tok = agent.run_agent(s1_message, "S1", token_limit=config.DEMO_SMALL_TOKEN_LIMIT, run_id="S1_token_limit_200")
    log_run(tok, "demo_token_limit")
    timeout = agent.run_agent(s1_message, "S1", time_limit_seconds=0, run_id="S1_time_limit_0")
    log_run(timeout, "demo_timeout")

    run_id = "S1_crash_resume"
    try:
        agent.run_agent(s1_message, "S1", run_id=run_id, crash_after_tools=2)
        raise RuntimeError("the simulated crash did not happen")
    except agent.SimulatedCrash as exc:
        log.warning("%s: %s", run_id, exc)
    saved = checkpoint.load(run_id)
    before, calls_before = saved["tools_executed"], saved["llm_calls"]
    resumed = agent.resume_agent(run_id)
    log_run(resumed, "crash_resume")
    return {"token_limit_200": summary_row(tok), "time_limit_0": summary_row(timeout),
            "crash_resume": {**summary_row(resumed), "tools_before_crash": before,
                             "tools_after_resume": resumed["tools_executed"][len(before):],
                             "llm_calls_before_crash": calls_before,
                             "llm_calls_after_resume": resumed["llm_calls"] - calls_before}}


def ledger_without_timestamps() -> list[dict]:
    """Ledger entries minus their timestamps, so the JSON report stays identical across re-runs."""
    lines = [json.loads(line) for line in config.REFUND_LEDGER.read_text(encoding="utf-8").splitlines()]
    return [{k: v for k, v in line.items() if k != "timestamp"} for line in lines]


def run() -> dict:
    """Run every Part D task and persist outputs/reports/part_d.json."""
    reset_outputs()
    chunks = chunk_documents()
    scenarios = pd.read_csv(config.AGENT_SCENARIOS, keep_default_na=False)
    s1_message = scenarios.set_index("scenario_id").loc["S1", "message"]
    report = {
        "chunks": {"total": len(chunks), "per_source": dict(Counter(c["source"] for c in chunks))},
        "retrieval_example": {"query": RETRIEVAL_EXAMPLE,
                              "top3": [{k: r[k] for k in ("source", "score")} for r in retrieve(RETRIEVAL_EXAMPLE)]},
        "evaluation": {"overlap_10": evaluation.evaluate(config.CHUNK_OVERLAP), "overlap_0": evaluation.evaluate(0)},
        "scenarios": run_scenarios(scenarios),
        "demos": run_demos(s1_message),
        "ledger_lines": ledger_without_timestamps(),
    }
    io_utils.write_json(config.report_path("d"), report)
    log.info("Part D report written to %s", config.report_path("d"))
    return report
