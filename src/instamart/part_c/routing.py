"""Routing rules that combine triage status, category and the Part B premium flag (task 7b)."""
import pandas as pd

from instamart import config

HUMAN_REVIEW_STATUSES = {"skipped_empty", "flagged_long", "flagged_invalid_output", "budget_exhausted"}


def route(status: str, category: str, is_premium: bool) -> tuple[str, str]:
    """Return (route, priority) for one ticket, applying the brief's rules in order."""
    if status in HUMAN_REVIEW_STATUSES:
        return "human_review", "NORMAL"
    if category == "fraud":
        return "security_team", "HIGH"
    if is_premium:
        return "premium_desk", "HIGH"
    return "support_queue", "NORMAL"


def load_segments() -> pd.DataFrame:
    """Read Part B's customer_segments.csv (customer_id, segment_name, is_premium)."""
    seg = pd.read_csv(config.CUSTOMER_SEGMENTS, usecols=["customer_id", "segment_name", "is_premium"])
    seg["is_premium"] = seg["is_premium"].astype(str).str.lower() == "true"
    return seg


def apply_routing(results: pd.DataFrame, segments: pd.DataFrame) -> pd.DataFrame:
    """Attach segment_name, route and priority; a customer missing from segments is not premium."""
    out = results.merge(segments, on="customer_id", how="left")
    out["segment_name"] = out["segment_name"].fillna("")
    out["is_premium"] = out["is_premium"].fillna(False).astype(bool)
    routed = [route(s, c, p) for s, c, p in zip(out["status"], out["category"], out["is_premium"])]
    out["route"] = [r for r, _ in routed]
    out["priority"] = [p for _, p in routed]
    return out[config.TRIAGE_COLUMNS]
