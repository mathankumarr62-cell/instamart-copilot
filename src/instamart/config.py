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

# Part C inputs, outputs and parameters (fixed by the brief)
TRIAGE_RESULTS = OUTPUTS_DIR / "triage_results.csv"
TRIAGE_BUDGET_DEMO = OUTPUTS_DIR / "triage_budget_demo.csv"
MAX_INPUT_TOKENS = 400
MAX_RETRIES = 3
BASE_DELAY = 0.05                               # seconds; wait before retry n = BASE_DELAY * 2**n * jitter
JITTER_RANGE = (0.9, 1.15)
RETRY_SEED = 42                                 # seeds the jitter generator so waits are reproducible
CATEGORIES = ["billing", "delivery", "technical", "fraud"]
DEMO_TOKEN_BUDGET = 6000
FINAL_TOKEN_BUDGET = 100000
TRIAGE_COLUMNS = ["ticket_id", "customer_id", "status", "category", "segment_name", "priority", "route",
                  "tokens_used"]

# Part D inputs, outputs and parameters (fixed by the brief)
POLICY_EVAL = RAW_DIR / "policy_eval.csv"
AGENT_SCENARIOS = RAW_DIR / "agent_scenarios.csv"
AGENT_RUNS = OUTPUTS_DIR / "agent_runs.jsonl"
REFUND_LEDGER = OUTPUTS_DIR / "refund_ledger.jsonl"
CHUNK_WORDS = 40
CHUNK_OVERLAP = 10
TOP_K = 3
REFUND_MIN_MINUTES = 45                         # delivered in MORE than this many minutes -> full refund
ESCALATION_THRESHOLD_INR = 1000.0               # refunds ABOVE this go to a human
AGENT_MAX_ITERATIONS = 6
AGENT_TOKEN_LIMIT = 6000
AGENT_TIME_LIMIT_SECONDS = 10
DEMO_SMALL_TOKEN_LIMIT = 200
