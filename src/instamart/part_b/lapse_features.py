"""Task 4: lapse cohort, label and leakage-safe features (orders before the cutoff + customer table only)."""
import pandas as pd

from instamart import config
from instamart.part_b.rfm import completed


def orders_before(orders: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Orders dated strictly before the cutoff; the only order rows features may see."""
    return orders[orders["order_ts"] < cutoff]


def lapse_labels(orders: pd.DataFrame, cohort: pd.Index, cutoff: pd.Timestamp,
                 window_end: pd.Timestamp) -> pd.Series:
    """lapsed = 1 when a cohort customer has no completed order with cutoff <= order_ts < window_end."""
    done = completed(orders)
    active = done.loc[(done["order_ts"] >= cutoff) & (done["order_ts"] < window_end), "customer_id"].unique()
    return pd.Series((~cohort.isin(active)).astype(int), index=cohort, name="lapsed")


def favourite_category(done: pd.DataFrame, products: pd.DataFrame) -> pd.Series:
    """Most frequent product category per customer (ties broken alphabetically for determinism)."""
    cat = done[["customer_id", "product_id"]].merge(products[["product_id", "category"]], on="product_id")
    counts = cat.groupby(["customer_id", "category"]).size().rename("n").reset_index()
    counts = counts.sort_values(["customer_id", "n", "category"], ascending=[True, False, True])
    return counts.drop_duplicates("customer_id").set_index("customer_id")["category"].rename("favourite_category")


def behaviour_features(before: pd.DataFrame, products: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Order-history features per customer with >= 1 completed order before the cutoff."""
    done = completed(before)
    feats = done.groupby("customer_id").agg(last_ts=("order_ts", "max"),
                                            frequency=("order_id", "nunique"),
                                            monetary=("order_amount", "sum"),
                                            avg_discount_pct=("discount_pct", "mean"),
                                            avg_delivery_minutes=("delivery_minutes", "mean"))
    feats["recency"] = (cutoff - feats["last_ts"]).dt.days
    final = before[before["status"].isin([config.STATUS_COMPLETED, config.STATUS_CANCELLED])]
    cancelled = final["status"].eq(config.STATUS_CANCELLED).groupby(final["customer_id"]).mean()
    feats["cancellation_rate"] = cancelled.reindex(feats.index)
    feats["favourite_category"] = favourite_category(done, products).reindex(feats.index)
    return feats.drop(columns="last_ts")


def build_lapse_dataset(orders: pd.DataFrame, customers: pd.DataFrame,
                        products: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Return (X, y) for the cohort, sorted by customer_id. X never sees orders on/after the cutoff
    and never uses segment labels."""
    cutoff, window_end = pd.Timestamp(config.LAPSE_CUTOFF), pd.Timestamp(config.LAPSE_WINDOW_END)
    before = orders_before(orders, cutoff)
    feats = behaviour_features(before, products, cutoff).sort_index()
    cust = customers.set_index("customer_id")
    feats = feats.join(cust[["city", "age", "gender"]])
    feats["tenure_days"] = (cutoff - cust.loc[feats.index, "signup_date"]).dt.days
    y = lapse_labels(orders, feats.index, cutoff, window_end)
    x = feats[config.LAPSE_NUMERIC + config.LAPSE_CATEGORICAL]
    return x, y


def assert_no_missing(x: pd.DataFrame) -> None:
    """Raise if any feature column contains a missing value."""
    missing = x.isna().sum()
    assert not missing.any(), f"missing feature values: {missing[missing > 0].to_dict()}"
