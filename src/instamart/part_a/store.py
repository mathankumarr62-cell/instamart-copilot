"""Task 5: write the clean tables to data/clean/*.csv and to the SQLite database data/instamart.db."""
import logging
import sqlite3

import pandas as pd

from instamart import config

log = logging.getLogger(__name__)


def to_storage_format(customers: pd.DataFrame, orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Render datetime columns as text: signup_date YYYY-MM-DD, order_ts YYYY-MM-DD HH:MM:SS."""
    cust = customers.copy()
    cust["signup_date"] = cust["signup_date"].dt.strftime(config.DATE_FORMAT)
    ords = orders.copy()
    ords["order_ts"] = ords["order_ts"].dt.strftime(config.TS_FORMAT)
    return cust, ords


def write_clean_csvs(customers: pd.DataFrame, products: pd.DataFrame, orders: pd.DataFrame) -> None:
    """Write the three clean tables to data/clean/."""
    config.CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    customers.to_csv(config.CLEAN_CUSTOMERS, index=False)
    products.to_csv(config.CLEAN_PRODUCTS, index=False)
    orders.to_csv(config.CLEAN_ORDERS, index=False)


def write_database(customers: pd.DataFrame, products: pd.DataFrame, orders: pd.DataFrame) -> dict:
    """Replace data/instamart.db with tables customers, products, orders and return their row counts."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.DB_PATH) as conn:
        for name, table in (("customers", customers), ("products", products), ("orders", orders)):
            table.to_sql(name, conn, if_exists="replace", index=False)
        counts = {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("customers", "products", "orders")}
    conn.close()
    log.info("database written to %s: %s", config.DB_PATH, counts)
    return counts


def store_all(customers: pd.DataFrame, products: pd.DataFrame, orders: pd.DataFrame) -> dict:
    """Persist clean tables as CSV and SQLite; return database row counts."""
    cust, ords = to_storage_format(customers, orders)
    write_clean_csvs(cust, products, ords)
    return write_database(cust, products, ords)
