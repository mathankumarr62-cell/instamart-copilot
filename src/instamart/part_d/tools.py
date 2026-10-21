"""The refund agent's five tools, their JSON-style specification and the name -> function map (task 5)."""
import contextvars
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from instamart import config
from instamart.part_d.retrieval import retrieve

LEDGER_PATH: Path = config.REFUND_LEDGER        # module attribute so tests can redirect the ledger
current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_run_id", default=None)


def get_order(order_id: str) -> dict:
    """Look the order up in data/instamart.db; return its refund-relevant fields or an error."""
    with sqlite3.connect(config.DB_PATH) as conn:
        row = conn.execute("SELECT order_id, status, order_amount, delivery_minutes FROM orders WHERE order_id = ?",
                           (order_id,)).fetchone()
    if row is None:
        return {"error": "order not found"}
    oid, status, amount, minutes = row
    return {"order_id": oid, "status": status, "order_amount": round(float(amount), 2),
            "delivery_minutes": None if minutes is None else float(minutes)}


def search_policy(query: str) -> dict:
    """Return the top policy chunks for the query under the key results."""
    return {"results": retrieve(query)}


def calculate_refund(order_amount: float, delivery_minutes: float | None, status: str = config.STATUS_COMPLETED) -> dict:
    """Completed and delivered in more than 45 minutes -> 100% of order_amount, otherwise 0."""
    late = delivery_minutes is not None and float(delivery_minutes) > config.REFUND_MIN_MINUTES
    refund = float(order_amount) if status == config.STATUS_COMPLETED and late else 0.0
    return {"refund_inr": round(refund, 2)}


def requires_escalation(refund_inr: float) -> bool:
    """A refund strictly above INR 1000 needs a human."""
    return float(refund_inr) > config.ESCALATION_THRESHOLD_INR


def _ledger_entry(tool: str, order_id: str) -> dict | None:
    """Return the existing ledger line for this tool and order_id, or None."""
    if not LEDGER_PATH.exists():
        return None
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line) if line.strip() else {}
        if entry.get("tool") == tool and entry.get("order_id") == order_id:
            return entry
    return None


def _record_once(tool: str, order_id: str, refund_inr: float) -> dict:
    """Append a ledger line unless one already exists for this tool and order_id (idempotent per order)."""
    existing = _ledger_entry(tool, order_id)
    if existing is not None:
        return {"refund_inr": round(float(existing["refund_inr"]), 2), "duplicate_prevented": True}
    _append_ledger(tool, order_id, refund_inr)
    return {"refund_inr": round(float(refund_inr), 2)}


def _append_ledger(tool: str, order_id: str, refund_inr: float) -> None:
    """Append one JSON line describing a refund action to the ledger."""
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tool": tool,
             "order_id": order_id, "refund_inr": round(float(refund_inr), 2), "run_id": current_run_id.get()}
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry) + "\n")


def issue_refund(order_id: str, refund_inr: float) -> dict:
    """Issue a refund of up to INR 1000 (larger amounts are refused and must be escalated)."""
    if requires_escalation(refund_inr):
        return {"error": "refund above INR 1000 must be escalated to a human"}
    return _record_once("issue_refund", order_id, refund_inr)


def escalate_to_human(order_id: str, refund_inr: float) -> dict:
    """Record the refund for a human support lead to approve."""
    return _record_once("escalate_to_human", order_id, refund_inr)


def _params(properties: dict, required: list[str]) -> dict:
    """JSON-schema style parameter block."""
    return {"type": "object", "properties": properties, "required": required}


TOOLS_SPEC = [
    {"name": "get_order", "description": "Look up an order's status, amount and delivery minutes by order id.",
     "parameters": _params({"order_id": {"type": "string"}}, ["order_id"])},
    {"name": "search_policy", "description": "Return the three policy passages most relevant to a query.",
     "parameters": _params({"query": {"type": "string"}}, ["query"])},
    {"name": "calculate_refund",
     "description": "Compute the refund in INR: full amount for a completed order delivered in more than 45 minutes, else 0.",
     "parameters": _params({"order_amount": {"type": "number"}, "delivery_minutes": {"type": ["number", "null"]},
                            "status": {"type": "string", "default": "completed"}},
                           ["order_amount", "delivery_minutes"])},
    {"name": "issue_refund", "description": "Issue a refund of at most INR 1000 and record it in the ledger.",
     "parameters": _params({"order_id": {"type": "string"}, "refund_inr": {"type": "number"}},
                           ["order_id", "refund_inr"])},
    {"name": "escalate_to_human", "description": "Send a refund above INR 1000 to a human support lead.",
     "parameters": _params({"order_id": {"type": "string"}, "refund_inr": {"type": "number"}},
                           ["order_id", "refund_inr"])},
]

TOOL_MAP = {"get_order": get_order, "search_policy": search_policy, "calculate_refund": calculate_refund,
            "issue_refund": issue_refund, "escalate_to_human": escalate_to_human}


def execute_tool(name: str, arguments: dict) -> dict:
    """Look the tool up in TOOL_MAP and call it; unknown tools and bad arguments become error observations."""
    func = TOOL_MAP.get(name)
    if func is None:
        return {"error": f"unknown tool {name}"}
    try:
        return func(**arguments)
    except (TypeError, ValueError) as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
