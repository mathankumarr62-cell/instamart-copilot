"""Task 6: load the seven named queries from sql/queries.sql and run each with pd.read_sql_query."""
import logging
import re
import sqlite3
from pathlib import Path

import pandas as pd

from instamart import config

log = logging.getLogger(__name__)

_HEADER = re.compile(r"^-- (Q\d+):.*$", re.M)


def load_queries(path: Path = config.QUERIES_PATH) -> dict[str, str]:
    """Split queries.sql into {'Q1': sql, ...} using the '-- Qn: ...' comment before each query."""
    text = path.read_text(encoding="utf-8")
    headers = list(_HEADER.finditer(text))
    queries = {}
    for i, match in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        queries[match.group(1)] = text[match.end():end].strip().rstrip(";")
    return queries


def run_queries(db_path: Path = config.DB_PATH) -> dict[str, pd.DataFrame]:
    """Execute every query against the database and return the result frames by name."""
    with sqlite3.connect(db_path) as conn:
        results = {name: pd.read_sql_query(sql, conn) for name, sql in load_queries().items()}
    conn.close()
    for name, df in results.items():
        log.info("%s returned %d rows", name, len(df))
    return results


def ties_rank_vs_row_number(q6: pd.DataFrame) -> int:
    """Count Q6 rows where RANK() differs from ROW_NUMBER() (only happens after a tie)."""
    return int((q6["rnk"] != q6["row_num"]).sum())


def summarise(results: dict[str, pd.DataFrame]) -> dict:
    """Return the reported figures for Q1-Q7."""
    q1, q2, q3, q4, q5, q6, q7 = (results[f"Q{i}"] for i in range(1, 8))
    top_cell = q2.loc[q2["revenue_inr"].idxmax()]
    tops = q6[q6["row_num"] == 1].sort_values("city")
    tied = q6[q6["rnk"] != q6["row_num"]]
    return {
        "Q1": {"customers": len(q1), "rows": q1},
        "Q2": {"rows": len(q2), "total_revenue_inr": round(float(q2["revenue_inr"].sum()), 2),
               "max_city": top_cell["city"], "max_category": top_cell["category"],
               "max_revenue_inr": float(top_cell["revenue_inr"]), "table": q2},
        "Q3": {"products": len(q3), "rows": q3},
        "Q4": {"customers": len(q4), "rows": q4},
        "Q5": {"customers": len(q5), "avg_spend_inr": float(q5["avg_spend_inr"].iloc[0])},
        "Q6": {"top_per_city": tops[["city", "customer_id", "total_spend"]],
               "rank_ne_row_number": ties_rank_vs_row_number(q6), "tied_rows": tied},
        "Q7": {"rows": len(q7), "first_day": q7["day"].iloc[0], "last_day": q7["day"].iloc[-1],
               "last_cumulative_inr": float(q7["cumulative_revenue_inr"].iloc[-1])},
    }
