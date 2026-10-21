"""Central paths and constants for the Instamart Copilot (all paths relative to the repo root)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLEAN_DIR = DATA_DIR / "clean"
POLICY_DIR = DATA_DIR / "policies"
DB_PATH = DATA_DIR / "instamart.db"

SQL_DIR = ROOT / "sql"
QUERIES_PATH = SQL_DIR / "queries.sql"

OUTPUTS_DIR = ROOT / "outputs"
REPORTS_DIR = OUTPUTS_DIR / "reports"
STATE_DIR = ROOT / "state"

RAW_CUSTOMERS = RAW_DIR / "customers.csv"
RAW_PRODUCTS = RAW_DIR / "products.csv"
RAW_ORDERS = RAW_DIR / "orders.csv"
RAW_TICKETS = RAW_DIR / "tickets.csv"

CLEAN_CUSTOMERS = CLEAN_DIR / "customers.csv"
CLEAN_PRODUCTS = CLEAN_DIR / "products.csv"
CLEAN_ORDERS = CLEAN_DIR / "orders.csv"

# Part A cleaning rules
AGE_MIN, AGE_MAX = 10, 100                      # ages outside this closed range are impossible
TS_FORMAT = "%Y-%m-%d %H:%M:%S"                 # order_ts storage format in CSV and SQLite
DATE_FORMAT = "%Y-%m-%d"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_PENDING = "pending"
GENDER_UNKNOWN = "unknown"
GENDER_MAP = {"male": "male", "m": "male", "female": "female", "f": "female"}  # keys are lower-cased
IQR_MULTIPLIER = 1.5
CORR_COLUMNS = ["order_amount", "discount_pct", "quantity", "delivery_minutes"]


def report_path(part: str) -> Path:
    """Return the JSON report path for a part letter, e.g. 'a' -> outputs/reports/part_a.json."""
    return REPORTS_DIR / f"part_{part.lower()}.json"
