"""Part B reference checkpoints, recomputed from the output files and part_b.json."""
import joblib
import pandas as pd

from instamart import config, io_utils
from instamart.part_b import lapse_features, lapse_model, rfm
from instamart.validation import Check

RFM_REFERENCE = {"customers": 1175, "recency_median": 19.0, "recency_min": 0, "recency_max": 180,
                 "frequency_mean": 9.46, "frequency_max": 33, "monetary_mean": 2552.06, "monetary_max": 14766.55}
K_REFERENCE = {2: (1820.8, 0.465), 3: (1268.2, 0.445), 4: (743.1, 0.526), 5: (617.4, 0.481),
               6: (503.2, 0.482), 7: (408.5, 0.416), 8: (366.5, 0.412)}
K4_SIZES = [436, 138, 419, 182]
SEGMENT_COLUMNS = ["customer_id", "recency", "frequency", "monetary", "segment_id", "segment_name", "is_premium"]
RETENTION_COLUMNS = ["customer_id", "lapse_probability", "actually_lapsed"]
APPROX = 0.05   # tolerance for model metrics the brief gives as "about"


def _rfm_checks(report: dict) -> list[Check]:
    """RFM summary statistics."""
    got = report["segments"]["rfm"]
    return [Check(f"RFM {k}", v, got[k]) for k, v in RFM_REFERENCE.items()]


def _kmeans_checks(report: dict) -> list[Check]:
    """Inertia (+-5%) and silhouette (+-0.05) for K=2..8."""
    sweep = {row["k"]: row for row in report["segments"]["k_sweep"]}
    out = []
    for k, (inertia, sil) in K_REFERENCE.items():
        out.append(Check(f"K={k} inertia", inertia, sweep[k]["inertia"], tol=0.05 * inertia))
        out.append(Check(f"K={k} silhouette", sil, sweep[k]["silhouette"], tol=0.05))
    return out


def _segment_checks(report: dict, segments: pd.DataFrame) -> list[Check]:
    """K=4 profile, PCA ratios and the customer_segments.csv contract."""
    profile = pd.DataFrame(report["segments"]["profile"])
    premium = profile.loc[profile["monetary"].idxmax()]
    loyal = profile.loc[profile["frequency"].idxmax()]
    means = segments.groupby("segment_id")["monetary"].mean()
    premium_ids = sorted(segments.loc[segments["is_premium"], "segment_id"].unique().tolist())
    ratios = report["segments"]["pca_explained_variance_ratio"]
    out = [Check("chosen K", 4, report["segments"]["chosen_k"])]
    out += [Check(f"K=4 segment of size ~{n} present", n, min(profile["size"], key=lambda s: abs(s - n)),
                  tol=0.05 * n) for n in K4_SIZES]
    out += [
        Check("K=4 premium segment size", 138, int(premium["size"]), tol=0.05 * 138),
        Check("K=4 premium mean monetary", 7130.0, float(premium["monetary"]), tol=0.02 * 7130),
        Check("K=4 premium mean frequency", 6.8, float(premium["frequency"]), tol=0.2),
        Check("K=4 most-frequent segment size", 419, int(loyal["size"]), tol=0.05 * 419),
        Check("K=4 most-frequent mean frequency", 19.4, float(loyal["frequency"]), tol=0.2),
        Check("K=4 most-frequent mean recency", 8.8, float(loyal["recency"]), tol=0.2),
        Check("PCA ratio PC1", 0.634, ratios[0], tol=0.02),
        Check("PCA ratio PC2", 0.218, ratios[1], tol=0.02),
        Check("PCA total", 0.852, report["segments"]["pca_total"], tol=0.02),
        Check("customer_segments.csv columns", SEGMENT_COLUMNS, list(segments.columns)),
        Check("customer_segments.csv rows", 1175, len(segments)),
        Check("is_premium = exactly the highest-mean-monetary segment", [int(means.idxmax())], premium_ids),
    ]
    return out


def _lapse_checks(report: dict) -> list[Check]:
    """Cohort, split, baseline, tuning, test metrics and oversampling."""
    lapse = report["lapse"]
    cohort, base, grid, test = lapse["cohort"], lapse["baseline"], lapse["grid_search"], lapse["test"]
    over = lapse["oversampling"]
    rf_best = grid["random_forest"]["best_params"]
    selected = lapse["selected_model"]
    return [
        Check("cohort customers", 1156, cohort["customers"]),
        Check("cohort lapsed", 443, cohort["lapsed"]),
        Check("cohort lapsed %", 38.32, cohort["lapsed_pct"]),
        Check("train rows", 924, cohort["train_rows"]),
        Check("test rows", 232, cohort["test_rows"]),
        Check("no missing feature values", 0, cohort["missing_feature_values"]),
        Check("baseline accuracy %", 61.6, round(100 * base["accuracy"], 1)),
        Check("baseline lapsed F1", 0.0, base["f1"]),
        Check("LR grid fits", 25, grid["logistic_regression"]["fits"]),
        Check("LR best C (reference 1; CV curve flat, brief allows differences)", 1,
              grid["logistic_regression"]["best_params"]["C"], gating=False),
        Check("LR test F1 ~0.62", 0.62, test["logistic_regression"]["f1"], tol=APPROX),
        Check("RF grid fits", 45, grid["random_forest"]["fits"]),
        Check("RF best max_depth / min_samples_leaf", (8, 10), (rf_best["max_depth"], rf_best["min_samples_leaf"])),
        Check("RF test F1 ~0.65", 0.65, test["random_forest"]["f1"], tol=APPROX),
        Check("selected model test F1 >= 0.55", True, test[selected]["f1"] >= 0.55),
        Check("oversampled class counts", {"0": 570, "1": 570}, over["class_counts"]),
        Check("LR recall before oversampling ~0.64", 0.64, over["original_lr"]["recall"], tol=APPROX),
        Check("LR recall after oversampling ~0.85", 0.85, over["balanced_lr"]["recall"], tol=APPROX),
        Check("LR precision after oversampling ~0.6", 0.6, over["balanced_lr"]["precision"], tol=APPROX),
        Check("precision does not rise after oversampling", True,
              over["balanced_lr"]["precision"] <= over["original_lr"]["precision"]),
    ]


def _artifact_checks(report: dict) -> list[Check]:
    """Reload the saved model, rebuild the test split and confirm it reproduces the reported test F1."""
    orders, customers = rfm.load_clean_orders(), rfm.load_clean_customers()
    products = pd.read_csv(config.CLEAN_PRODUCTS)
    x, y = lapse_features.build_lapse_dataset(orders, customers, products)
    _, x_test, _, y_test = lapse_model.split(x, y)
    model = joblib.load(config.LAPSE_MODEL)
    f1 = lapse_model.lapsed_metrics(y_test, model.predict(x_test))["f1"]
    retention = pd.read_csv(config.RETENTION_LIST)
    selected = report["lapse"]["selected_model"]
    return [
        Check("reloaded lapse_model.joblib reproduces test F1", report["lapse"]["test"][selected]["f1"], f1),
        Check("retention_list.csv columns", RETENTION_COLUMNS, list(retention.columns)),
        Check("retention_list.csv rows <= 10", True, 0 < len(retention) <= config.RETENTION_TOP_N),
        Check("retention_list.csv truly lapsed matches report", report["lapse"]["retention_list"]["truly_lapsed"],
              int(retention["actually_lapsed"].sum())),
    ]


def build_checks() -> list[Check]:
    """Return every Part B checkpoint."""
    report = io_utils.read_json(config.report_path("b"))
    segments = pd.read_csv(config.CUSTOMER_SEGMENTS)
    return (_rfm_checks(report) + _kmeans_checks(report) + _segment_checks(report, segments)
            + _lapse_checks(report) + _artifact_checks(report))
