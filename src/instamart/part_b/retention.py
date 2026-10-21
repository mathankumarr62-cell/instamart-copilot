"""Task 8c: illustrative retention list of Premium test customers ranked by lapse probability."""
import pandas as pd
from sklearn.pipeline import Pipeline

from instamart import config


def retention_list(model: Pipeline, x_test: pd.DataFrame, y_test: pd.Series,
                   segments: pd.DataFrame) -> pd.DataFrame:
    """Top-N Premium test customers by predicted lapse probability, with the true label."""
    premium_ids = set(segments.loc[segments["is_premium"], "customer_id"])
    mask = x_test.index.isin(premium_ids)
    out = pd.DataFrame({
        "customer_id": x_test.index[mask],
        "lapse_probability": model.predict_proba(x_test[mask])[:, 1].round(4),
        "actually_lapsed": y_test[mask].to_numpy(),
    })
    out = out.sort_values(["lapse_probability", "customer_id"], ascending=[False, True])
    return out.head(config.RETENTION_TOP_N).reset_index(drop=True)


def write_retention_list(rows: pd.DataFrame) -> dict:
    """Write outputs/retention_list.csv and return the reported counts."""
    rows.to_csv(config.RETENTION_LIST, index=False)
    return {"rows": int(len(rows)), "truly_lapsed": int(rows["actually_lapsed"].sum())}
