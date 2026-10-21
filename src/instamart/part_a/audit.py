"""Task 2: audit the raw exports (shape, dtypes, missingness and the twelve audit figures)."""
import logging

import pandas as pd

from instamart import config

log = logging.getLogger(__name__)


def profile_table(df: pd.DataFrame) -> dict:
    """Return shape, dtypes and per-column missing count/percentage for one table."""
    missing = df.isna().sum()
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "missing": {
            c: {"count": int(missing[c]), "pct": round(100.0 * missing[c] / len(df), 2)} for c in df.columns
        },
    }


def order_audit_figures(orders: pd.DataFrame) -> dict:
    """Compute the raw orders.csv audit figures."""
    amount_text = orders["order_amount"]
    non_numeric = amount_text.notna() & pd.to_numeric(amount_text, errors="coerce").isna()
    delivery = pd.to_numeric(orders["delivery_minutes"], errors="coerce")
    return {
        "orders_rows": int(len(orders)),
        "exact_duplicate_rows": int(orders.duplicated().sum()),
        "pending_rows": int((orders["status"] == config.STATUS_PENDING).sum()),
        "distinct_order_id": int(orders["order_id"].nunique()),
        "non_numeric_amounts": int(non_numeric.sum()),
        "negative_delivery_minutes": int((delivery < 0).sum()),
        "blank_delivery_minutes": int(orders["delivery_minutes"].isna().sum()),
    }


def customer_audit_figures(customers: pd.DataFrame) -> dict:
    """Compute the raw customers.csv audit figures."""
    age = customers["age"]
    return {
        "blank_age": int(age.isna().sum()),
        "age_outside_10_100": int((age.notna() & ~age.between(config.AGE_MIN, config.AGE_MAX)).sum()),
        "raw_city_spellings": int(customers["city"].nunique()),
        "raw_gender_spellings": int(customers["gender"].dropna().nunique()),
        "blank_gender": int(customers["gender"].isna().sum()),
    }


def run_audit(customers: pd.DataFrame, products: pd.DataFrame, orders: pd.DataFrame) -> dict:
    """Audit the three raw tables and return profiles plus the twelve audit figures."""
    figures = {**order_audit_figures(orders), **customer_audit_figures(customers)}
    log.info("audit figures: %s", figures)
    return {
        "tables": {
            "customers": profile_table(customers),
            "products": profile_table(products),
            "orders": profile_table(orders),
        },
        "figures": figures,
    }
