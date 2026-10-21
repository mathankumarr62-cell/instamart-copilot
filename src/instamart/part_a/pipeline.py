"""Part A orchestration: audit -> clean -> store -> SQL -> EDA, then write outputs/reports/part_a.json."""
import logging

from instamart import config, io_utils
from instamart.part_a import audit, clean_customers, clean_orders, eda, sql_analysis, store

log = logging.getLogger(__name__)


def run() -> dict:
    """Run every Part A task in order and return (and persist) the report dictionary."""
    raw_customers = io_utils.read_raw_customers()
    products = io_utils.read_raw_products()
    raw_orders = io_utils.read_raw_orders()

    audit_report = audit.run_audit(raw_customers, products, raw_orders)

    customers, customer_rules = clean_customers.clean_customers(raw_customers)
    orders, order_rules = clean_orders.clean_orders(raw_orders, products)

    db_counts = store.store_all(customers, products, orders)

    sql_results = sql_analysis.run_queries()
    sql_summary = sql_analysis.summarise(sql_results)

    eda_report = eda.run_eda(orders, customers, products, sql_summary["Q2"]["total_revenue_inr"])

    report = {
        "audit": audit_report,
        "cleaning_rules": {"customers": customer_rules, "orders": order_rules},
        "customers_clean": clean_customers.customer_summary(customers),
        "orders_clean": clean_orders.order_summary(orders),
        "database_row_counts": db_counts,
        "sql": sql_summary,
        "eda": eda_report,
    }
    io_utils.write_json(config.report_path("a"), report)
    log.info("Part A report written to %s", config.report_path("a"))
    return report
