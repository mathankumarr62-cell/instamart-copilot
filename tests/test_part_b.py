"""Unit tests for Part B: RFM, lapse labels and the leakage guard (standard-library unittest only)."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from instamart import config  # noqa: E402
from instamart.part_b import lapse_features, rfm  # noqa: E402

PRODUCTS = pd.DataFrame({"product_id": ["P1", "P2"], "category": ["Dairy", "Electronics"]})
CUSTOMERS = pd.DataFrame({
    "customer_id": ["C1", "C2", "C3"], "city": ["Pune", "Delhi", "Pune"], "age": [30.0, 40.0, 50.0],
    "gender": ["male", "female", "unknown"],
    "signup_date": pd.to_datetime(["2024-01-01", "2024-06-01", "2025-01-01"]),
})


def orders_frame(rows: list[tuple]) -> pd.DataFrame:
    """Build an orders table from (order_id, customer_id, product_id, ts, status, amount, discount, delivery)."""
    df = pd.DataFrame(rows, columns=["order_id", "customer_id", "product_id", "order_ts", "status",
                                     "order_amount", "discount_pct", "delivery_minutes"])
    df["order_ts"] = pd.to_datetime(df["order_ts"])
    df["quantity"] = 1
    return df


BASE_ORDERS = orders_frame([
    ("O1", "C1", "P1", "2025-08-01 10:00:00", "completed", 100.0, 0, 20.0),
    ("O2", "C1", "P1", "2025-08-20 10:00:00", "completed", 50.0, 10, 30.0),
    ("O3", "C1", "P2", "2025-08-25 10:00:00", "cancelled", 999.0, 0, None),
    ("O4", "C2", "P2", "2025-07-01 10:00:00", "completed", 1500.0, 20, 50.0),
    ("O5", "C1", "P1", "2025-09-10 10:00:00", "completed", 80.0, 0, 15.0),    # September: C1 active
    ("O6", "C3", "P1", "2025-09-15 10:00:00", "completed", 60.0, 0, 15.0),    # C3 only after cutoff
])


class RfmTest(unittest.TestCase):
    def test_rfm_counts_only_completed_orders(self):
        table = rfm.build_rfm(BASE_ORDERS, pd.Timestamp("2025-10-01")).set_index("customer_id")
        self.assertEqual(table.loc["C1"].tolist(), [20, 3, 230.0])     # last 2025-09-10 10:00 -> 20 whole days
        self.assertEqual(table.loc["C2"].tolist(), [91, 1, 1500.0])
        self.assertEqual(sorted(table.index), ["C1", "C2", "C3"])

    def test_customer_with_only_cancelled_orders_is_excluded(self):
        only_cancelled = orders_frame([("X", "C9", "P1", "2025-08-01 10:00:00", "cancelled", 10.0, 0, None)])
        self.assertTrue(rfm.build_rfm(only_cancelled, pd.Timestamp("2025-10-01")).empty)


class LapseLabelTest(unittest.TestCase):
    def test_label_and_cohort(self):
        x, y = lapse_features.build_lapse_dataset(BASE_ORDERS, CUSTOMERS, PRODUCTS)
        self.assertEqual(list(x.index), ["C1", "C2"])           # C3 has no completed order before cutoff
        self.assertEqual(y.to_dict(), {"C1": 0, "C2": 1})

    def test_cancelled_september_order_does_not_count_as_active(self):
        extra = orders_frame([("O7", "C2", "P1", "2025-09-05 10:00:00", "cancelled", 10.0, 0, None)])
        _, y = lapse_features.build_lapse_dataset(pd.concat([BASE_ORDERS, extra]), CUSTOMERS, PRODUCTS)
        self.assertEqual(y["C2"], 1)

    def test_features_from_before_cutoff(self):
        x, _ = lapse_features.build_lapse_dataset(BASE_ORDERS, CUSTOMERS, PRODUCTS)
        c1 = x.loc["C1"]
        # last completed 2025-08-20 10:00 -> 11 whole days before the 2025-09-01 00:00 cutoff
        self.assertEqual((c1["recency"], c1["frequency"], c1["monetary"]), (11, 2, 150.0))
        self.assertAlmostEqual(c1["cancellation_rate"], 1 / 3)
        self.assertEqual(c1["favourite_category"], "Dairy")
        self.assertEqual(c1["tenure_days"], (pd.Timestamp(config.LAPSE_CUTOFF) - pd.Timestamp("2024-01-01")).days)


class LeakageGuardTest(unittest.TestCase):
    def test_orders_before_excludes_cutoff_and_later(self):
        cutoff = pd.Timestamp(config.LAPSE_CUTOFF)
        boundary = orders_frame([("B", "C1", "P1", config.LAPSE_CUTOFF, "completed", 1.0, 0, 10.0)])
        before = lapse_features.orders_before(pd.concat([BASE_ORDERS, boundary]), cutoff)
        self.assertTrue((before["order_ts"] < cutoff).all())
        self.assertNotIn("B", set(before["order_id"]))

    def test_features_unchanged_by_orders_on_or_after_cutoff(self):
        x_before, _ = lapse_features.build_lapse_dataset(BASE_ORDERS, CUSTOMERS, PRODUCTS)
        future = orders_frame([
            ("F1", "C2", "P1", config.LAPSE_CUTOFF, "completed", 5000.0, 40, 70.0),
            ("F2", "C1", "P2", "2025-09-30 23:59:59", "cancelled", 3000.0, 0, None),
        ])
        x_after, y_after = lapse_features.build_lapse_dataset(pd.concat([BASE_ORDERS, future]), CUSTOMERS, PRODUCTS)
        pd.testing.assert_frame_equal(x_before, x_after)
        self.assertEqual(y_after["C2"], 0)                       # the future order changes only the label

    def test_segment_labels_are_not_features(self):
        self.assertFalse({"segment_id", "segment_name", "is_premium"} & set(config.LAPSE_NUMERIC + config.LAPSE_CATEGORICAL))


if __name__ == "__main__":
    unittest.main()
