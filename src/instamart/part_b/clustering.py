"""Tasks 2-3: K-means sweep on scaled RFM, segment profiles and names, PCA projection."""
import logging

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from instamart import config

log = logging.getLogger(__name__)

PREMIUM_NAME = "Premium Big Spenders"
SEGMENT_ACTIONS = {
    PREMIUM_NAME: "Assign a priority support line and early access to new electronics launches.",
    "Loyal Regulars": "Reward with a subscription-style loyalty pass to protect their weekly basket.",
    "Dormant / Lapsing": "Send a time-limited win-back coupon on their favourite grocery staples.",
    "Occasional Shoppers": "Nudge a second monthly order with a free-delivery threshold reminder.",
}


def scale_rfm(rfm: pd.DataFrame) -> np.ndarray:
    """Standardise recency, frequency and monetary (mean 0, unit variance)."""
    return StandardScaler().fit_transform(rfm[config.RFM_COLUMNS])


def fit_kmeans(x: np.ndarray, k: int) -> KMeans:
    """Fit KMeans with the brief's fixed n_init and random_state."""
    return KMeans(n_clusters=k, n_init=config.KMEANS_N_INIT, random_state=config.RANDOM_STATE).fit(x)


def k_sweep(x: np.ndarray) -> pd.DataFrame:
    """Inertia and silhouette for every K in K_RANGE."""
    rows = []
    for k in config.K_RANGE:
        model = fit_kmeans(x, k)
        rows.append({"k": k, "inertia": round(float(model.inertia_), 1),
                     "silhouette": round(float(silhouette_score(x, model.labels_)), 3)})
    return pd.DataFrame(rows)


def name_segments(profile: pd.DataFrame) -> dict[int, str]:
    """Derive business names from the profile values (never from cluster ids): highest mean monetary
    is Premium, then highest recency is Dormant, then highest frequency is Loyal, the rest Occasional."""
    names: dict[int, str] = {}
    remaining = profile.copy()
    for column, name in (("monetary", PREMIUM_NAME), ("recency", "Dormant / Lapsing"),
                         ("frequency", "Loyal Regulars")):
        if remaining.empty:
            break
        seg = int(remaining[column].idxmax())
        names[seg] = name
        remaining = remaining.drop(index=seg)
    for i, seg in enumerate(remaining.index):
        names[int(seg)] = "Occasional Shoppers" if i == 0 else f"Occasional Shoppers {i + 1}"
    return names


def profile_segments(rfm: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    """Size and mean R/F/M per segment, with business name, action and premium flag."""
    df = rfm.assign(segment_id=labels)
    profile = df.groupby("segment_id").agg(size=("customer_id", "count"), recency=("recency", "mean"),
                                           frequency=("frequency", "mean"), monetary=("monetary", "mean"))
    names = name_segments(profile)
    profile["segment_name"] = profile.index.map(names)
    profile["action"] = profile["segment_name"].map(lambda n: SEGMENT_ACTIONS.get(n, SEGMENT_ACTIONS["Occasional Shoppers"]))
    profile["is_premium"] = profile.index == profile["monetary"].idxmax()
    return profile.round({"recency": 1, "frequency": 1, "monetary": 2}).reset_index()


def pca_ratios(x: np.ndarray) -> list[float]:
    """Explained variance ratio of a 2-component PCA on the scaled RFM matrix."""
    pca = PCA(n_components=config.PCA_COMPONENTS, random_state=config.RANDOM_STATE).fit(x)
    return [round(float(r), 4) for r in pca.explained_variance_ratio_]


def segment_table(rfm: pd.DataFrame, labels: np.ndarray, profile: pd.DataFrame) -> pd.DataFrame:
    """Per-customer segment file with the brief's columns."""
    meta = profile.set_index("segment_id")
    out = rfm.assign(segment_id=labels)
    out["segment_name"] = out["segment_id"].map(meta["segment_name"])
    out["is_premium"] = out["segment_id"].map(meta["is_premium"]).astype(bool)
    return out[["customer_id", "recency", "frequency", "monetary", "segment_id", "segment_name", "is_premium"]]


def run_clustering(rfm: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Sweep K, fit the chosen K, profile/name segments, project with PCA, write customer_segments.csv."""
    x = scale_rfm(rfm)
    sweep = k_sweep(x)
    log.info("K sweep:\n%s", sweep.to_string(index=False))
    labels = fit_kmeans(x, config.CHOSEN_K).labels_
    profile = profile_segments(rfm, labels)
    segments = segment_table(rfm, labels, profile)
    config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    segments.to_csv(config.CUSTOMER_SEGMENTS, index=False)
    ratios = pca_ratios(x)
    log.info("segments written to %s; PCA ratios %s", config.CUSTOMER_SEGMENTS, ratios)
    return segments, {"k_sweep": sweep, "chosen_k": config.CHOSEN_K, "profile": profile,
                      "pca_explained_variance_ratio": ratios, "pca_total": round(sum(ratios), 4)}
