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

# Part B outputs
CUSTOMER_SEGMENTS = OUTPUTS_DIR / "customer_segments.csv"
LAPSE_MODEL = OUTPUTS_DIR / "lapse_model.joblib"
RETENTION_LIST = OUTPUTS_DIR / "retention_list.csv"

# Part B parameters (fixed by the brief)
RANDOM_STATE = 42
SNAPSHOT_TS = "2025-10-01 00:00:00"             # RFM snapshot moment
LAPSE_CUTOFF = "2025-09-01 00:00:00"            # features use orders strictly before this
LAPSE_WINDOW_END = "2025-10-01 00:00:00"        # label window: cutoff <= order_ts < window end (September)
RFM_COLUMNS = ["recency", "frequency", "monetary"]
K_RANGE = range(2, 9)
KMEANS_N_INIT = 10
CHOSEN_K = 4                                    # chosen from {3, 4, 5}; reasoning in the README
PCA_COMPONENTS = 2
TEST_SIZE = 0.2
CV_FOLDS = 5
LR_MAX_ITER = 1000
LR_GRID = {"model__C": [0.01, 0.1, 1, 10, 100]}
RF_N_ESTIMATORS = 100
RF_GRID = {"model__max_depth": [3, 5, 8], "model__min_samples_leaf": [5, 10, 20]}
LAPSE_CATEGORICAL = ["city", "gender", "favourite_category"]
LAPSE_NUMERIC = ["recency", "frequency", "monetary", "avg_discount_pct", "cancellation_rate",
                 "avg_delivery_minutes", "age", "tenure_days"]
RETENTION_TOP_N = 10


def report_path(part: str) -> Path:
    """Return the JSON report path for a part letter, e.g. 'a' -> outputs/reports/part_a.json."""
    return REPORTS_DIR / f"part_{part.lower()}.json"
