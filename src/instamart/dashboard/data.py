"""Read-only views for the dashboard API, built from outputs/reports/part_<x>.json and the graded files.

Nothing here writes to disk: reports, CSVs and JSONL files are only read, and SQLite is opened read-only."""
import json
import re
import sqlite3
import threading
from functools import lru_cache

import joblib
import pandas as pd

from instamart import checkpoints, config, io_utils
from instamart.part_a import sql_analysis
from instamart.part_b import lapse_features, lapse_model, rfm
from instamart.validation import Check

# Live demos temporarily redirect config.STATE_DIR, so check building and demos share one lock.
STATE_LOCK = threading.RLock()

SQL_PREVIEW_ROWS = 200
README = config.ROOT / "README.md"              # source of the written explanations shown on the dashboard
CUSTOMER_ID = re.compile(r"C\d{4}")                     # used with fullmatch
RETENTION_CAVEAT = ("The Premium flag comes from whole-window RFM, which includes the September lapse window, "
                    "so it is a post-hoc label: this retention list is illustrative and not a leakage-free evaluation.")
_SQL_HEADER = re.compile(r"^-- (Q\d+): (.+?) - (.*)", re.M)


def report(part: str) -> dict:
    """Load outputs/reports/part_<part>.json."""
    return io_utils.read_json(config.report_path(part))


def _check_row(part: str, check: Check) -> dict:
    """JSON view of one checkpoint."""
    status = "INFO" if not check.gating else "PASS" if check.passed else "FAIL"
    return {"part": part, "name": check.name, "expected": repr(check.expected), "actual": repr(check.actual),
            "tolerance": check.tol or None, "status": status}


@lru_cache(maxsize=1)
def _cached_checks() -> tuple[dict, ...]:
    """Build every checkpoint once per process (about 3 s); refresh=True in checkpoint_status rebuilds."""
    with STATE_LOCK:
        return tuple(_check_row(part, check) for part, check in checkpoints.collect())


def checkpoint_status(refresh: bool = False) -> dict:
    """All checkpoints with PASS/FAIL/INFO plus the gating pass count, reusing validate.py's list."""
    if refresh:
        _cached_checks.cache_clear()
    rows = list(_cached_checks())
    gating = [r for r in rows if r["status"] != "INFO"]
    passed = sum(r["status"] == "PASS" for r in gating)
    return {"passed": passed, "total": len(gating), "all_passed": passed == len(gating), "checks": rows}


def _scenarios_as_expected(scenarios: list[dict]) -> int:
    """Scenarios whose status starts with the expected outcome (S7 expects any FALLBACK_*)."""
    return sum(s["status"].startswith(s["expected_outcome"]) for s in scenarios)


def overview(refresh: bool = False) -> dict:
    """Headline KPIs from all four reports plus the checkpoint table."""
    a, b, c, d = (report(p) for p in "abcd")
    kpis = {
        "clean_orders": a["orders_clean"]["rows"],
        "completed_orders": a["orders_clean"]["completed"],
        "completed_revenue_inr": a["orders_clean"]["completed_revenue_inr"],
        "customers": a["customers_clean"]["rows"],
        "customers_with_orders": b["segments"]["rfm"]["customers"],
        "segments": b["segments"]["chosen_k"],
        "lapse_rate_pct": b["lapse"]["cohort"]["lapsed_pct"],
        "tickets_triaged": c["tickets"],
        "few_shot_accuracy_pct": c["few_shot"]["accuracy_pct"],
        "scenarios_passed": _scenarios_as_expected(d["scenarios"]),
        "scenarios_total": len(d["scenarios"]),
    }
    return {"kpis": kpis, "checkpoints": checkpoint_status(refresh)}


def _sql_headers() -> dict[str, dict]:
    """Technique and description of each query from its '-- Qn: technique - description' header."""
    text = config.QUERIES_PATH.read_text(encoding="utf-8")
    return {m.group(1): {"technique": m.group(2).strip(), "description": m.group(3).strip()}
            for m in _SQL_HEADER.finditer(text)}


def _read_only_connection() -> sqlite3.Connection:
    """Open data/instamart.db in SQLite read-only mode."""
    return sqlite3.connect(f"file:{config.DB_PATH.as_posix()}?mode=ro", uri=True)


def sql_results(limit: int = SQL_PREVIEW_ROWS) -> dict[str, dict]:
    """Run Q1-Q7 read-only and return SQL text, columns, the first `limit` rows and the row count."""
    headers, out = _sql_headers(), {}
    with _read_only_connection() as conn:
        for name, sql in sql_analysis.load_queries().items():
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            out[name] = {**headers.get(name, {}), "sql": sql + ";", "columns": [c[0] for c in cursor.description],
                         "rows": [list(r) for r in rows[:limit]], "row_count": len(rows)}
    conn.close()
    return out


def _plain(text: str) -> str:
    """Markdown paragraph as plain text: drop bold markers and code backticks, join wrapped lines."""
    return " ".join(text.replace("**", "").replace("`", "").split())


@lru_cache(maxsize=1)
def _readme_sections() -> dict[str, list[str]]:
    """README.md paragraphs keyed by their '## ' or '### ' heading (written explanations live only there)."""
    sections, current = {}, None
    for block in re.split(r"\n\s*\n", README.read_text(encoding="utf-8")):
        block = block.strip()
        heading = re.match(r"#{2,3} (.+)", block)
        if heading:
            current = heading.group(1).strip()
            sections[current] = []
        elif current and block:
            sections[current].append(block)
    return sections


def _readme_bold(section: str, lead: str) -> tuple[str, str]:
    """(bold lead, rest) of the paragraph in `section` that starts with **lead...; empty strings if absent."""
    for block in _readme_sections().get(section, []):
        m = re.match(r"\*\*(" + re.escape(lead) + r".*?)\*\*\s*(.*)", block, re.S)
        if m:
            return m.group(1).rstrip(".:").strip(), _plain(m.group(2))
    return "", ""


def readme_notes() -> dict:
    """Written explanations from README.md: EDA answers, the inertia note, TF-IDF and ReAct versus plan-and-execute."""
    eda = [_readme_bold("pandas cross-check and exploratory analysis", q) for q in
           ("What is this data", "What do the distributions", "Are there outliers", "What relationships")]
    tfidf_lead, tfidf = _readme_bold("Chunking and retrieval", "TF-IDF in two sentences")
    explanation, _, limitation = tfidf.partition("Limitation:")
    return {
        "eda_answers": [{"question": q, "answer": a} for q, a in eda if q],
        "inertia": _readme_bold("K-means on standardised R, F, M (n_init=10, random_state=42)", "Why inertia")[1],
        "tfidf": {"explanation": explanation.strip(), "limitation": limitation.strip()} if tfidf_lead else None,
        "react_vs_plan": [_plain(p) for p in _readme_sections().get("ReAct versus plan-and-execute", [])],
    }


def part_a() -> dict:
    """Audit, cleaning-rule log, before/after counts, SQL Q1-Q7 (summary + live result tables) and EDA."""
    a = report("a")
    queries = sql_results()
    for name, summary in a["sql"].items():
        queries[name]["summary"] = {k: v for k, v in summary.items() if not isinstance(v, list)}
    return {"audit": a["audit"], "cleaning_rules": a["cleaning_rules"], "customers_clean": a["customers_clean"],
            "orders_clean": a["orders_clean"], "database_row_counts": a["database_row_counts"],
            "sql": queries, "eda": a["eda"], "notes": readme_notes()}


def part_b() -> dict:
    """Segments (K table, profiles, PCA) and the lapse model results, with the retention-list caveat."""
    b = report("b")
    return {"segments": b["segments"], "lapse": b["lapse"], "retention_caveat": RETENTION_CAVEAT, "notes": readme_notes()}


def part_c() -> dict:
    """Triage report plus every row of outputs/triage_results.csv."""
    rows = pd.read_csv(config.TRIAGE_RESULTS, keep_default_na=False)
    return {**report("c"), "triage_rows": io_utils.records(rows)}


def _agent_runs() -> list[dict]:
    """Every line of outputs/agent_runs.jsonl (read only)."""
    text = config.AGENT_RUNS.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def scenarios() -> list[dict]:
    """The seven rows of data/raw/agent_scenarios.csv."""
    return io_utils.records(pd.read_csv(config.AGENT_SCENARIOS, keep_default_na=False))


def part_d() -> dict:
    """Chunk counts, RAG evaluation, scenario table with traces, stop-safely demos and the resume trace."""
    d = report("d")
    runs = {r["run_id"]: r for r in _agent_runs()}
    brief = {s["scenario_id"]: s for s in scenarios()}
    table = [{**s, "message": brief.get(s["scenario_id"], {}).get("message", ""),
              "customer_id": brief.get(s["scenario_id"], {}).get("customer_id", ""),
              "steps": runs.get(s["run_id"], {}).get("steps", []),
              "final_answer": runs.get(s["run_id"], {}).get("final_answer", "")} for s in d["scenarios"]]
    demos = {k: {**v, "final_answer": runs.get(v["run_id"], {}).get("final_answer", ""),
                 "steps": runs.get(v["run_id"], {}).get("steps", [])} for k, v in d["demos"].items()}
    return {"chunks": d["chunks"], "retrieval_example": d["retrieval_example"], "evaluation": d["evaluation"],
            "scenarios": table, "demos": demos, "ledger_lines": d["ledger_lines"],
            "example_questions": [r["question"] for r in d["evaluation"]["overlap_10"]["rows"]], "notes": readme_notes()}


@lru_cache(maxsize=1)
def _lapse_scores() -> pd.DataFrame:
    """Lapse probability of every cohort customer from the saved model, plus test-set membership and label."""
    orders, customers = rfm.load_clean_orders(), rfm.load_clean_customers()
    products = pd.read_csv(config.CLEAN_PRODUCTS)
    x, y = lapse_features.build_lapse_dataset(orders, customers, products)
    _, x_test, _, _ = lapse_model.split(x, y)
    model = joblib.load(config.LAPSE_MODEL)
    return pd.DataFrame({"lapse_probability": model.predict_proba(x)[:, 1].round(4), "actually_lapsed": y,
                         "in_test_set": x.index.isin(x_test.index)}, index=x.index)


def customer(customer_id: str) -> dict | None:
    """Segment, RFM, profile and (for the lapse cohort) model lapse probability of one customer, or None."""
    segments = pd.read_csv(config.CUSTOMER_SEGMENTS).set_index("customer_id")
    profile = pd.read_csv(config.CLEAN_CUSTOMERS).set_index("customer_id")
    if customer_id not in profile.index:
        return None
    out = {"customer_id": customer_id, **io_utils.records(profile.loc[[customer_id]])[0],
           "segment": None, "lapse": None}
    if customer_id in segments.index:
        seg = io_utils.records(segments.loc[[customer_id]])[0]
        out["segment"] = {**seg, "is_premium": str(seg["is_premium"]).lower() == "true"}
    scores = _lapse_scores()
    if customer_id in scores.index:
        out["lapse"] = io_utils.records(scores.loc[[customer_id]])[0]
    return out
