"""Task 7: pandas cross-check of Q2 and exploratory statistics on completed order amounts."""
import logging

import numpy as np
import pandas as pd

from instamart import config

log = logging.getLogger(__name__)


def completed_with_dims(orders: pd.DataFrame, customers: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """Return completed orders joined with customer city and product category."""
    done = orders[orders["status"] == config.STATUS_COMPLETED]
    return (done.merge(customers[["customer_id", "city"]], on="customer_id", how="left")
                .merge(products[["product_id", "category"]], on="product_id", how="left"))


def revenue_pivot(completed: pd.DataFrame) -> pd.DataFrame:
    """Rebuild Q2 as a city x category pivot with margins (grand total in ['All', 'All'])."""
    return pd.pivot_table(completed, values="order_amount", index="city", columns="category",
                          aggfunc="sum", margins=True, margins_name="All")


def city_aggregates(completed: pd.DataFrame) -> pd.DataFrame:
    """Per-city sum, mean and count of completed order_amount using named aggregation."""
    agg = completed.groupby("city").agg(sum_inr=("order_amount", "sum"),
                                        mean_inr=("order_amount", "mean"),
                                        count=("order_amount", "count"))
    return agg.round({"sum_inr": 2, "mean_inr": 2}).reset_index()


def amount_statistics(amount: pd.Series) -> dict:
    """Mean, median, skewness, quartiles, 1.5 x IQR fences and outlier counts beyond each fence."""
    q1, q3 = float(amount.quantile(0.25)), float(amount.quantile(0.75))
    iqr = q3 - q1
    lower, upper = q1 - config.IQR_MULTIPLIER * iqr, q3 + config.IQR_MULTIPLIER * iqr
    return {
        "count": int(amount.count()),
        "mean": round(float(amount.mean()), 2),
        "median": round(float(amount.median()), 2),
        "std": round(float(amount.std()), 2),
        "min": round(float(amount.min()), 2),
        "max": round(float(amount.max()), 2),
        "skewness": round(float(amount.skew()), 4),
        "q1": round(q1, 2),
        "q3": round(q3, 2),
        "iqr": round(iqr, 2),
        "lower_fence": round(lower, 2),
        "upper_fence": round(upper, 2),
        "outliers_below": int((amount < lower).sum()),
        "outliers_above": int((amount > upper).sum()),
    }


def correlation_summary(completed: pd.DataFrame) -> dict:
    """Correlation matrix of the four numeric columns and the off-diagonal pair with largest |r|."""
    corr = completed[config.CORR_COLUMNS].astype(float).corr()
    mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)
    pairs = corr.where(mask).stack().dropna()
    strongest = pairs.abs().idxmax()
    return {
        "matrix": corr.round(4).to_dict(),
        "pairs": [{"a": a, "b": b, "r": round(float(r), 4)} for (a, b), r in pairs.items()],
        "strongest": {"a": strongest[0], "b": strongest[1], "r": round(float(pairs[strongest]), 4)},
    }


def run_eda(orders: pd.DataFrame, customers: pd.DataFrame, products: pd.DataFrame, sql_total: float) -> dict:
    """Run the pandas cross-check and the exploratory statistics; return the reported figures."""
    completed = completed_with_dims(orders, customers, products)
    pivot = revenue_pivot(completed)
    grand_total = round(float(pivot.loc["All", "All"]), 2)
    log.info("pivot grand total %.2f vs SQL total %.2f", grand_total, sql_total)
    return {
        "pivot_grand_total_inr": grand_total,
        "sql_q2_total_inr": sql_total,
        "pivot_matches_sql": abs(grand_total - sql_total) < 0.005,
        "city_aggregates": city_aggregates(completed),
        "amount_stats": amount_statistics(completed["order_amount"]),
        "correlation": correlation_summary(completed),
    }
