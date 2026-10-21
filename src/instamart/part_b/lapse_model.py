"""Tasks 5-8: leakage-free preprocessing, baseline, grid searches, test evaluation, oversampling,
interpretation and persistence of the lapse model."""
import logging

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils import resample

from instamart import config

log = logging.getLogger(__name__)


def split(x: pd.DataFrame, y: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Stratified 80/20 split with the brief's random_state."""
    return train_test_split(x, y, test_size=config.TEST_SIZE, stratify=y, random_state=config.RANDOM_STATE)


def make_preprocessor() -> ColumnTransformer:
    """k-1 one-hot columns for nominal features, standard scaling for numeric ones."""
    return ColumnTransformer([
        ("cat", OneHotEncoder(drop="first", handle_unknown="ignore"), config.LAPSE_CATEGORICAL),
        ("num", StandardScaler(), config.LAPSE_NUMERIC),
    ])


def make_pipeline(model) -> Pipeline:
    """Preprocessor + estimator, so every transform is fitted on training rows only."""
    return Pipeline([("prep", make_preprocessor()), ("model", model)])


def lapsed_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict:
    """Accuracy, confusion matrix and lapsed-class (positive) precision/recall/F1."""
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
    }


def baseline(y_test: pd.Series) -> dict:
    """Always predict 'not lapsed' on the test set."""
    return lapsed_metrics(y_test, np.zeros(len(y_test), dtype=int))


def tune(estimator, grid: dict, x_train: pd.DataFrame, y_train: pd.Series) -> GridSearchCV:
    """GridSearchCV over a preprocessing+model pipeline (cv=5, scoring='f1'), training rows only."""
    search = GridSearchCV(make_pipeline(estimator), grid, cv=config.CV_FOLDS, scoring="f1")
    return search.fit(x_train, y_train)


def search_summary(search: GridSearchCV) -> dict:
    """Best parameters, best CV F1 and number of fits of a finished grid search."""
    params = {k.removeprefix("model__"): v for k, v in search.best_params_.items()}
    n_candidates = len(search.cv_results_["params"])
    return {"best_params": params, "best_cv_f1": round(float(search.best_score_), 4),
            "fits": n_candidates * config.CV_FOLDS}


def scaler_frequency_check(pipe: Pipeline, x: pd.DataFrame) -> dict:
    """Fitted scaler's mean of frequency (training rows) next to the full-cohort mean."""
    scaler = pipe.named_steps["prep"].named_transformers_["num"]
    idx = config.LAPSE_NUMERIC.index("frequency")
    return {"scaler_mean_frequency": round(float(scaler.mean_[idx]), 4),
            "cohort_mean_frequency": round(float(x["frequency"].mean()), 4)}


def oversample(x_train: pd.DataFrame, y_train: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Keep every training row and add lapsed duplicates (with replacement, random_state=42)
    until both classes have equal counts."""
    minority = x_train[y_train == 1]
    extra_n = int((y_train == 0).sum() - (y_train == 1).sum())
    extra = resample(minority, replace=True, n_samples=extra_n, random_state=config.RANDOM_STATE)
    x_bal = pd.concat([x_train, extra])
    y_bal = pd.concat([y_train, pd.Series(1, index=extra.index, name=y_train.name)])
    return x_bal, y_bal


def feature_names(pipe: Pipeline) -> list[str]:
    """Output feature names of the fitted preprocessor without transformer prefixes."""
    return [n.split("__", 1)[1] for n in pipe.named_steps["prep"].get_feature_names_out()]


def top_importances(rf_pipe: Pipeline, n: int = 5) -> list[dict]:
    """The n largest random-forest feature importances."""
    imp = pd.Series(rf_pipe.named_steps["model"].feature_importances_, index=feature_names(rf_pipe))
    return [{"feature": f, "importance": round(float(v), 4)} for f, v in imp.nlargest(n).items()]


def lr_coefficients(lr_pipe: Pipeline) -> list[dict]:
    """All logistic-regression coefficients (on scaled / one-hot features) sorted by |value|."""
    coef = pd.Series(lr_pipe.named_steps["model"].coef_[0], index=feature_names(lr_pipe))
    coef = coef.reindex(coef.abs().sort_values(ascending=False).index)
    return [{"feature": f, "coef": round(float(v), 4), "sign": "+" if v > 0 else "-"} for f, v in coef.items()]


def persist_and_reload(model: Pipeline, x_test: pd.DataFrame) -> bool:
    """joblib.dump the model, reload it and confirm identical test predictions."""
    config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, config.LAPSE_MODEL)
    reloaded = joblib.load(config.LAPSE_MODEL)
    identical = bool(np.array_equal(model.predict(x_test), reloaded.predict(x_test)))
    assert identical, "reloaded model predictions differ"
    log.info("model saved to %s; reload reproduces predictions: %s", config.LAPSE_MODEL, identical)
    return identical


def choose_model(results: dict[str, dict]) -> str:
    """Select the tuned model with the higher lapsed-class test F1 (computed once, after tuning)."""
    return max(results, key=lambda name: results[name]["f1"])
