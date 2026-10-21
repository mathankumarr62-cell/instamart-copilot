"""Part B orchestration: RFM -> K-means segments -> lapse dataset -> tuned models -> retention list."""
import logging

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from instamart import config, io_utils
from instamart.part_b import clustering, lapse_features, lapse_model, retention, rfm

log = logging.getLogger(__name__)


def run_segments(orders: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Tasks 1-3: RFM table, K sweep, chosen-K profile, PCA, customer_segments.csv."""
    table = rfm.build_rfm(orders, pd.Timestamp(config.SNAPSHOT_TS))
    segments, cluster_report = clustering.run_clustering(table)
    return segments, {"rfm": rfm.rfm_summary(table), **cluster_report}


def run_lapse(orders: pd.DataFrame, customers: pd.DataFrame, products: pd.DataFrame,
              segments: pd.DataFrame) -> dict:
    """Tasks 4-8: cohort, split, baseline, tuning, test evaluation, oversampling, interpretation."""
    x, y = lapse_features.build_lapse_dataset(orders, customers, products)
    lapse_features.assert_no_missing(x)
    x_train, x_test, y_train, y_test = lapse_model.split(x, y)

    lr_search = lapse_model.tune(LogisticRegression(max_iter=config.LR_MAX_ITER), config.LR_GRID, x_train, y_train)
    rf_search = lapse_model.tune(RandomForestClassifier(n_estimators=config.RF_N_ESTIMATORS,
                                                        random_state=config.RANDOM_STATE),
                                 config.RF_GRID, x_train, y_train)
    lr, rf = lr_search.best_estimator_, rf_search.best_estimator_
    scaler_check = lapse_model.scaler_frequency_check(lr, x)
    log.info("scaler mean of frequency (train) %.4f vs full cohort %.4f",
             scaler_check["scaler_mean_frequency"], scaler_check["cohort_mean_frequency"])

    # The test set is used only from here on, after both searches have finished.
    test = {"logistic_regression": lapse_model.lapsed_metrics(y_test, lr.predict(x_test)),
            "random_forest": lapse_model.lapsed_metrics(y_test, rf.predict(x_test))}
    selected_name = lapse_model.choose_model(test)
    selected = {"logistic_regression": lr, "random_forest": rf}[selected_name]

    x_bal, y_bal = lapse_model.oversample(x_train, y_train)
    lr_bal = lapse_model.make_pipeline(LogisticRegression(max_iter=config.LR_MAX_ITER,
                                                          C=lr_search.best_params_["model__C"]))
    lr_bal.fit(x_bal, y_bal)

    reload_ok = lapse_model.persist_and_reload(selected, x_test)
    retention_rows = retention.retention_list(selected, x_test, y_test, segments)

    return {
        "cohort": {"customers": int(len(y)), "lapsed": int(y.sum()),
                   "lapsed_pct": round(100.0 * float(y.mean()), 2),
                   "train_rows": int(len(y_train)), "test_rows": int(len(y_test)),
                   "train_lapsed": int(y_train.sum()), "test_lapsed": int(y_test.sum()),
                   "features": config.LAPSE_NUMERIC + config.LAPSE_CATEGORICAL,
                   "missing_feature_values": int(x.isna().sum().sum())},
        "scaler_check": scaler_check,
        "baseline": lapse_model.baseline(y_test),
        "grid_search": {"logistic_regression": lapse_model.search_summary(lr_search),
                        "random_forest": lapse_model.search_summary(rf_search)},
        "test": test,
        "selected_model": selected_name,
        "oversampling": {"class_counts": {str(k): int(v) for k, v in y_bal.value_counts().sort_index().items()},
                         "original_lr": test["logistic_regression"],
                         "balanced_lr": lapse_model.lapsed_metrics(y_test, lr_bal.predict(x_test))},
        "rf_top_importances": lapse_model.top_importances(rf),
        "lr_coefficients": lapse_model.lr_coefficients(lr),
        "model_reload_identical": reload_ok,
        "retention_list": {**retention.write_retention_list(retention_rows), "table": retention_rows},
    }


def run() -> dict:
    """Run every Part B task in order and persist outputs/reports/part_b.json."""
    orders, customers = rfm.load_clean_orders(), rfm.load_clean_customers()
    products = pd.read_csv(config.CLEAN_PRODUCTS)
    segments, segment_report = run_segments(orders)
    report = {"segments": segment_report, "lapse": run_lapse(orders, customers, products, segments)}
    io_utils.write_json(config.report_path("b"), report)
    log.info("Part B report written to %s", config.report_path("b"))
    return report
