"""Task 4: clean orders in the exact order the brief prescribes, counting what each rule changes."""
import logging

import pandas as pd

from instamart import config

log = logging.getLogger(__name__)


def parse_order_ts(df: pd.DataFrame) -> pd.DataFrame:
    """Step 1: convert order_ts text to datetime."""
    out = df.copy()
    out["order_ts"] = pd.to_datetime(out["order_ts"], format=config.TS_FORMAT)
    return out


def drop_exact_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Step 2: remove rows that are identical in every column (first occurrence kept)."""
    return df.drop_duplicates(keep="first")


def keep_latest_record(df: pd.DataFrame) -> pd.DataFrame:
    """Step 3: for each order_id keep only the record with the latest order_ts."""
    ordered = df.sort_values(["order_id", "order_ts"], kind="stable")
    return ordered.drop_duplicates(subset="order_id", keep="last").reset_index(drop=True)


def expected_amount(price_inr: float, quantity: float, discount_pct: float) -> float:
    """Amount formula from the brief: round(price_inr * quantity * (1 - discount_pct / 100), 2)."""
    return round(price_inr * quantity * (1 - discount_pct / 100), 2)


def fill_amounts(df: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """Step 4: make order_amount numeric (junk -> missing) and fill missing amounts from the price formula."""
    out = df.copy()
    out["order_amount"] = pd.to_numeric(out["order_amount"], errors="coerce")
    price = out["product_id"].map(products.set_index("product_id")["price_inr"])
    missing = out["order_amount"].isna()
    out.loc[missing, "order_amount"] = [
        expected_amount(p, q, d)
        for p, q, d in zip(price[missing], out.loc[missing, "quantity"], out.loc[missing, "discount_pct"])
    ]
    return out


def negative_delivery_to_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Step 5a: impossible negative delivery_minutes become missing."""
    out = df.copy()
    out["delivery_minutes"] = out["delivery_minutes"].mask(out["delivery_minutes"] < 0)
    return out


def fill_completed_delivery(df: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """Step 5b: fill completed orders' missing delivery_minutes with their category's median among
    completed orders (groupby + transform); cancelled orders are left missing on purpose."""
    out = df.copy()
    completed = out["status"] == config.STATUS_COMPLETED
    category = out["product_id"].map(products.set_index("product_id")["category"])
    done = out.loc[completed, "delivery_minutes"]
    category_median = done.groupby(category[completed]).transform("median")
    out.loc[completed, "delivery_minutes"] = done.fillna(category_median)
    return out


def clean_orders(raw: pd.DataFrame, products: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Run steps 1-5 in order and return the clean table and a list of {rule, changed} records."""
    rules: list[dict] = []

    df = parse_order_ts(raw)
    rules.append({"rule": "order_ts: text converted to datetime", "changed": int(df["order_ts"].notna().sum())})

    before = len(df)
    df = drop_exact_duplicates(df)
    rules.append({"rule": "exact duplicate rows removed", "changed": before - len(df)})

    before = len(df)
    df = keep_latest_record(df)
    rules.append({"rule": "earlier records of the same order_id removed (latest order_ts kept)",
                  "changed": before - len(df)})

    junk = int((df["order_amount"].notna() & pd.to_numeric(df["order_amount"], errors="coerce").isna()).sum())
    rules.append({"rule": "order_amount: unparseable text set to missing", "changed": junk})
    missing_before = int(pd.to_numeric(df["order_amount"], errors="coerce").isna().sum())
    df = fill_amounts(df, products)
    rules.append({"rule": "order_amount: missing filled from price formula",
                  "changed": missing_before - int(df["order_amount"].isna().sum())})

    negatives = int((df["delivery_minutes"] < 0).sum())
    df = negative_delivery_to_missing(df)
    rules.append({"rule": "delivery_minutes: negative set to missing", "changed": negatives})

    missing_before = int(df["delivery_minutes"].isna().sum())
    df = fill_completed_delivery(df, products)
    rules.append({"rule": "delivery_minutes: completed orders filled with category median (groupby + transform)",
                  "changed": missing_before - int(df["delivery_minutes"].isna().sum())})

    log.info("orders cleaned: %d rows", len(df))
    return df, rules


def order_summary(orders: pd.DataFrame) -> dict:
    """Return the post-cleaning reference figures for the orders table."""
    status = orders["status"]
    completed, cancelled = status == config.STATUS_COMPLETED, status == config.STATUS_CANCELLED
    return {
        "rows": int(len(orders)),
        "distinct_order_id": int(orders["order_id"].nunique()),
        "completed": int(completed.sum()),
        "cancelled": int(cancelled.sum()),
        "pending": int((status == config.STATUS_PENDING).sum()),
        "missing_order_amount": int(orders["order_amount"].isna().sum()),
        "missing_delivery_completed": int(orders.loc[completed, "delivery_minutes"].isna().sum()),
        "missing_delivery_cancelled": int(orders.loc[cancelled, "delivery_minutes"].isna().sum()),
        "completed_revenue_inr": round(float(orders.loc[completed, "order_amount"].sum()), 2),
    }
