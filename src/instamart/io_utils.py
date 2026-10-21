"""Shared input/output helpers: raw-table loading, JSON reports and logging setup."""
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from instamart import config


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging once for an entry script."""
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def read_raw_csv(path: Path) -> pd.DataFrame:
    """Read a raw export treating only empty cells as missing, so junk text such as 'N/A' stays visible."""
    return pd.read_csv(path, keep_default_na=False, na_values=[""])


def read_raw_customers() -> pd.DataFrame:
    """Load data/raw/customers.csv exactly as exported."""
    return read_raw_csv(config.RAW_CUSTOMERS)


def read_raw_products() -> pd.DataFrame:
    """Load data/raw/products.csv exactly as exported."""
    return read_raw_csv(config.RAW_PRODUCTS)


def read_raw_orders() -> pd.DataFrame:
    """Load data/raw/orders.csv exactly as exported (order_amount stays text because of junk values)."""
    return read_raw_csv(config.RAW_ORDERS)


def read_raw_tickets() -> pd.DataFrame:
    """Load data/raw/tickets.csv keeping empty texts as empty strings (keep_default_na=False)."""
    return pd.read_csv(config.RAW_TICKETS, keep_default_na=False)


def _to_jsonable(value: Any) -> Any:
    """Convert numpy/pandas scalars and containers into plain JSON types."""
    if isinstance(value, pd.DataFrame):
        return _to_jsonable(value.to_dict(orient="records"))
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime(config.TS_FORMAT)
    return value


def write_json(path: Path, payload: dict) -> None:
    """Write a dictionary as pretty-printed UTF-8 JSON, creating parent folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_to_jsonable(payload), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


def read_json(path: Path) -> dict:
    """Read a JSON report written by write_json."""
    return json.loads(path.read_text(encoding="utf-8"))


def records(df: pd.DataFrame) -> list[dict]:
    """Return a DataFrame as a JSON-friendly list of row dictionaries."""
    return _to_jsonable(df.to_dict(orient="records"))
