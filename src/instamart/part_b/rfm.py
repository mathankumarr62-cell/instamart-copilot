"""Task 1: recency / frequency / monetary per customer from completed orders."""
import pandas as pd

from instamart import config


def load_clean_orders() -> pd.DataFrame:
    """Read data/clean/orders.csv with order_ts parsed as datetime."""
    orders = pd.read_csv(config.CLEAN_ORDERS)
    orders["order_ts"] = pd.to_datetime(orders["order_ts"], format=config.TS_FORMAT)
    return orders


def load_clean_customers() -> pd.DataFrame:
    """Read data/clean/customers.csv with signup_date parsed as datetime."""
    customers = pd.read_csv(config.CLEAN_CUSTOMERS)
    customers["signup_date"] = pd.to_datetime(customers["signup_date"], format=config.DATE_FORMAT)
    return customers


def completed(orders: pd.DataFrame) -> pd.DataFrame:
    """Return only completed orders."""
    return orders[orders["status"] == config.STATUS_COMPLETED]


def build_rfm(orders: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """RFM for every customer with a completed order: recency = (as_of - last order).dt.days,
    frequency = distinct completed orders, monetary = sum of completed order_amount."""
    done = completed(orders)
    rfm = done.groupby("customer_id").agg(last_ts=("order_ts", "max"),
                                          frequency=("order_id", "nunique"),
                                          monetary=("order_amount", "sum"))
    rfm["recency"] = (as_of - rfm["last_ts"]).dt.days
    rfm["monetary"] = rfm["monetary"].round(2)
    return rfm.reset_index()[["customer_id", *config.RFM_COLUMNS]]


def rfm_summary(rfm: pd.DataFrame) -> dict:
    """Reported RFM statistics."""
    return {
        "customers": int(len(rfm)),
        "recency_median": float(rfm["recency"].median()),
        "recency_min": int(rfm["recency"].min()),
        "recency_max": int(rfm["recency"].max()),
        "frequency_mean": round(float(rfm["frequency"].mean()), 2),
        "frequency_max": int(rfm["frequency"].max()),
        "monetary_mean": round(float(rfm["monetary"].mean()), 2),
        "monetary_max": round(float(rfm["monetary"].max()), 2),
    }
