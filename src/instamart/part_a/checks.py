"""Part A reference checkpoints, recomputed from the clean CSVs, the SQLite database and part_a.json."""
import sqlite3

import pandas as pd

from instamart import config, io_utils
from instamart.part_a import sql_analysis
from instamart.validation import Check, money

AUDIT_REFERENCE = {
    "orders_rows": 13084, "exact_duplicate_rows": 119, "pending_rows": 656, "distinct_order_id": 12309,
    "non_numeric_amounts": 120, "negative_delivery_minutes": 106, "blank_delivery_minutes": 2541,
    "blank_age": 61, "age_outside_10_100": 6, "raw_city_spellings": 24, "raw_gender_spellings": 10,
    "blank_gender": 30,
}
CITY_REFERENCE = {"Pune": 227, "Delhi": 210, "Bengaluru": 197, "Chennai": 191, "Hyderabad": 191, "Mumbai": 184}
GENDER_REFERENCE = {"female": 610, "male": 560, "unknown": 30}
TOP_PER_CITY_REFERENCE = [
    ("Bengaluru", "C0082", 12856.20), ("Chennai", "C0930", 10151.40), ("Delhi", "C0291", 13742.60),
    ("Hyderabad", "C0743", 12730.05), ("Mumbai", "C0693", 14766.55), ("Pune", "C0426", 10377.10),
]
TOTAL_REVENUE = 2998668.80


def _audit_checks(report: dict) -> list[Check]:
    """Checks on the twelve raw audit figures."""
    figures = report["audit"]["figures"]
    return [Check(f"audit {k}", v, figures[k]) for k, v in AUDIT_REFERENCE.items()]


def _customer_checks(customers: pd.DataFrame) -> list[Check]:
    """Checks on data/clean/customers.csv."""
    return [
        Check("customers city counts", CITY_REFERENCE, customers["city"].value_counts().to_dict()),
        Check("customers gender counts", GENDER_REFERENCE, customers["gender"].value_counts().to_dict()),
        Check("customers missing age", 0, int(customers["age"].isna().sum())),
        Check("customers ages all within 18-60", True, bool(customers["age"].between(18, 60).all())),
    ]


def _order_checks(orders: pd.DataFrame) -> list[Check]:
    """Checks on data/clean/orders.csv."""
    completed = orders["status"] == config.STATUS_COMPLETED
    cancelled = orders["status"] == config.STATUS_CANCELLED
    return [
        Check("orders rows", 12309, len(orders)),
        Check("orders one row per order_id", True, bool(orders["order_id"].is_unique)),
        Check("orders completed", 11110, int(completed.sum())),
        Check("orders cancelled", 1199, int(cancelled.sum())),
        Check("orders pending", 0, int((orders["status"] == config.STATUS_PENDING).sum())),
        Check("orders missing order_amount", 0, int(orders["order_amount"].isna().sum())),
        Check("orders missing delivery (completed)", 0, int(orders.loc[completed, "delivery_minutes"].isna().sum())),
        Check("orders missing delivery (cancelled)", 1199, int(orders.loc[cancelled, "delivery_minutes"].isna().sum())),
        Check("orders completed revenue INR", TOTAL_REVENUE, money(orders.loc[completed, "order_amount"].sum())),
    ]


def _database_checks() -> list[Check]:
    """Checks on data/instamart.db tables and the order_ts text format."""
    with sqlite3.connect(config.DB_PATH) as conn:
        tables = sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))
        bad_ts = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE order_ts NOT GLOB "
            "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'").fetchone()[0]
    conn.close()
    return [
        Check("db tables", ["customers", "orders", "products"], tables),
        Check("db order_ts stored as YYYY-MM-DD HH:MM:SS text", 0, bad_ts),
    ]


def _sql_checks() -> list[Check]:
    """Re-run sql/queries.sql against the database and check Q1-Q7."""
    r = sql_analysis.run_queries()
    q6 = r["Q6"]
    tops = q6[q6["row_num"] == 1].sort_values("city")
    top_tuples = [(c, cid, money(s)) for c, cid, s in zip(tops["city"], tops["customer_id"], tops["total_spend"])]
    q2 = r["Q2"].sort_values("revenue_inr", ascending=False).iloc[0]
    return [
        Check("Q1 customers", 30, len(r["Q1"])),
        Check("Q2 rows", 30, len(r["Q2"])),
        Check("Q2 revenue total INR", TOTAL_REVENUE, money(r["Q2"]["revenue_inr"].sum())),
        Check("Q2 largest cell", ("Bengaluru", "Electronics", 233909.45),
              (q2["city"], q2["category"], money(q2["revenue_inr"]))),
        Check("Q3 products", 11, len(r["Q3"])),
        Check("Q4 customers", 25, len(r["Q4"])),
        Check("Q5 customers", 550, len(r["Q5"])),
        Check("Q5 average INR", 2552.06, money(r["Q5"]["avg_spend_inr"].iloc[0])),
        Check("Q6 top customer per city", TOP_PER_CITY_REFERENCE, top_tuples),
        Check("Q6 rows with RANK != ROW_NUMBER", 8, sql_analysis.ties_rank_vs_row_number(q6)),
        Check("Q7 daily rows", 183, len(r["Q7"])),
        Check("Q7 last cumulative INR", TOTAL_REVENUE, money(r["Q7"]["cumulative_revenue_inr"].iloc[-1])),
    ]


def _eda_checks(report: dict) -> list[Check]:
    """Checks on the pandas cross-check and exploratory statistics."""
    eda = report["eda"]
    cities = {row["city"]: row for row in eda["city_aggregates"]}
    stats, strongest = eda["amount_stats"], eda["correlation"]["strongest"]
    return [
        Check("EDA pivot grand total equals SQL total", TOTAL_REVENUE, eda["pivot_grand_total_inr"]),
        Check("EDA Bengaluru sum/mean/count", (523643.40, 276.47, 1894),
              (cities["Bengaluru"]["sum_inr"], cities["Bengaluru"]["mean_inr"], cities["Bengaluru"]["count"])),
        Check("EDA Mumbai sum/mean/count", (479058.50, 297.00, 1613),
              (cities["Mumbai"]["sum_inr"], cities["Mumbai"]["mean_inr"], cities["Mumbai"]["count"])),
        Check("EDA mean", 269.91, stats["mean"]),
        Check("EDA median", 135.00, stats["median"]),
        Check("EDA skewness", 4.61, stats["skewness"], tol=0.01),
        Check("EDA Q1", 64.80, stats["q1"]),
        Check("EDA Q3", 297.00, stats["q3"]),
        Check("EDA upper fence", 645.30, stats["upper_fence"]),
        Check("EDA outliers above", 897, stats["outliers_above"]),
        Check("EDA outliers below", 0, stats["outliers_below"]),
        Check("EDA strongest |corr| pair", ("order_amount", "discount_pct"), (strongest["a"], strongest["b"])),
        Check("EDA strongest corr value", -0.095, strongest["r"], tol=0.001),
    ]


def build_checks() -> list[Check]:
    """Return every Part A checkpoint."""
    report = io_utils.read_json(config.report_path("a"))
    customers = pd.read_csv(config.CLEAN_CUSTOMERS)
    orders = pd.read_csv(config.CLEAN_ORDERS)
    return (_audit_checks(report) + _customer_checks(customers) + _order_checks(orders)
            + _database_checks() + _sql_checks() + _eda_checks(report))
