"""Unit tests for Part A cleaning rules (standard-library unittest only)."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from instamart.part_a import clean_customers, clean_orders  # noqa: E402


class GenderMappingTest(unittest.TestCase):
    def test_all_raw_spellings_map_to_three_values(self):
        raw = pd.Series(["male", "Male", "M", "m", "MALE", "female", "Female", "F", "f", "FEMALE", None])
        expected = ["male"] * 5 + ["female"] * 5 + ["unknown"]
        self.assertEqual(clean_customers.map_gender(raw).tolist(), expected)

    def test_unrecognised_spelling_is_unknown(self):
        self.assertEqual(clean_customers.map_gender(pd.Series(["x"])).tolist(), ["unknown"])


class CityStandardisationTest(unittest.TestCase):
    def test_strip_and_title_case(self):
        raw = pd.Series([" Chennai ", "MUMBAI", "bengaluru", "Delhi"])
        self.assertEqual(clean_customers.standardise_city(raw).tolist(),
                         ["Chennai", "Mumbai", "Bengaluru", "Delhi"])


class AgeRuleTest(unittest.TestCase):
    def test_impossible_ages_filled_with_city_median(self):
        df = pd.DataFrame({"city": ["Pune", "Pune", "Pune", "Delhi", "Delhi"],
                           "age": [20.0, 40.0, 999.0, None, 50.0]})
        df["age"] = clean_customers.invalidate_impossible_ages(df["age"])
        self.assertEqual(clean_customers.fill_age_by_city_median(df).tolist(), [20.0, 40.0, 30.0, 50.0, 50.0])


class AmountFormulaTest(unittest.TestCase):
    def test_formula_rounds_to_two_decimals(self):
        self.assertEqual(clean_orders.expected_amount(129, 2, 0), 258.0)
        self.assertEqual(clean_orders.expected_amount(245, 1, 5), 232.75)
        self.assertEqual(clean_orders.expected_amount(1499, 2, 15), 2548.3)

    def test_junk_amounts_filled_from_price(self):
        products = pd.DataFrame({"product_id": ["P001"], "price_inr": [129]})
        orders = pd.DataFrame({"product_id": ["P001"] * 3, "quantity": [1, 2, 1],
                               "discount_pct": [0, 10, 0], "order_amount": ["N/A", "error", "100.5"]})
        self.assertEqual(clean_orders.fill_amounts(orders, products)["order_amount"].tolist(), [129.0, 232.2, 100.5])


class LatestRecordTest(unittest.TestCase):
    def test_keeps_latest_order_ts_per_order(self):
        df = pd.DataFrame({
            "order_id": ["ORD-1", "ORD-1", "ORD-2"],
            "order_ts": pd.to_datetime(["2025-05-01 10:05:00", "2025-05-01 10:00:00", "2025-05-02 09:00:00"]),
            "status": ["completed", "pending", "cancelled"],
        })
        out = clean_orders.keep_latest_record(df)
        self.assertEqual(out["order_id"].tolist(), ["ORD-1", "ORD-2"])
        self.assertEqual(out["status"].tolist(), ["completed", "cancelled"])

    def test_exact_duplicates_dropped_before_latest_rule(self):
        df = pd.DataFrame({"order_id": ["ORD-1", "ORD-1"], "order_ts": ["2025-05-01 10:00:00"] * 2})
        self.assertEqual(len(clean_orders.drop_exact_duplicates(df)), 1)


class DeliveryFillTest(unittest.TestCase):
    def test_completed_filled_with_category_median_cancelled_left_missing(self):
        products = pd.DataFrame({"product_id": ["P1", "P2"], "category": ["Dairy", "Snacks"]})
        df = pd.DataFrame({"product_id": ["P1", "P1", "P1", "P2", "P1"],
                           "status": ["completed", "completed", "completed", "completed", "cancelled"],
                           "delivery_minutes": [10.0, 30.0, -10.0, 50.0, None]})
        df = clean_orders.negative_delivery_to_missing(df)
        out = clean_orders.fill_completed_delivery(df, products)["delivery_minutes"]
        self.assertEqual(out.iloc[:4].tolist(), [10.0, 30.0, 20.0, 50.0])
        self.assertTrue(pd.isna(out.iloc[4]))


if __name__ == "__main__":
    unittest.main()
