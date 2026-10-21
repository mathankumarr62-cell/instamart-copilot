# Instamart Customer Intelligence & Support Copilot

## Overview

This is an internal Copilot for the (fictional, synthetic) Swiggy Instamart customer-experience team, built in four connected Parts:

- **Part A**: turns messy raw exports into a trusted SQLite database and answers business questions in SQL and pandas.
- **Part B**: customer segments and lapse prediction.
- **Part C**: support-ticket triage with guardrails.
- **Part D**: a policy RAG assistant and a refund agent.

Everything runs offline. It uses only the Python standard library, pandas, numpy, scikit-learn and joblib. Every language-model call goes through the supplied `mock_llm.py`, so no API key or network connection is needed. All money is in INR.

Layout: thin entry scripts at the root (`part_a.py`, `run_all.py`, `validate.py`) and the code in `src/instamart/`. Paths and constants live in `config.py`, with one module per task under `part_a/`. The SQL is in `sql/queries.sql` and the unit tests are in `tests/`. Every reported number is written to `outputs/reports/part_<x>.json`.

## Reproduce

Run these from the repository root (Python 3.11 or newer):

1. `python -m venv .venv`
2. Activate the environment:
   - Windows (PowerShell): `.venv\Scripts\Activate.ps1` (cmd: `.venv\Scripts\activate.bat`)
   - macOS/Linux: `source .venv/bin/activate`
3. `python -m pip install -r requirements.txt`
4. `python generate_data.py` (last line: `generated: customers=1200 products=40 orders_raw=13084 tickets=164`)
5. `python run_all.py`
6. `python -m unittest`
7. `python validate.py` (last line: `ALL CHECKPOINTS PASSED`)

## Part A

### Audit of the raw exports

| Table | Rows | Columns | Columns with missing values (count, %) |
|---|---|---|---|
| customers.csv | 1,200 | 5 | age 61 (5.08%), gender 30 (2.50%); all others 0 |
| products.csv | 40 | 4 | none |
| orders.csv | 13,084 | 9 | delivery_minutes 2,541 (19.42%); all others 0 |

Data types as loaded: `age` and `delivery_minutes` are float64, while `quantity`, `discount_pct` and `price_inr` are int64. All other columns are text, including `order_amount`, because it contains junk entries. Only empty cells count as missing. This keeps text such as `N/A` visible as an unparseable amount instead of letting pandas silently turn it into NaN.

| Audit figure | Value |
|---|---|
| Raw orders.csv rows | 13,084 |
| Exact duplicate rows | 119 |
| Rows with status pending | 656 |
| Distinct order_id | 12,309 |
| order_amount entries that are not numbers | 120 |
| Negative delivery_minutes | 106 |
| Blank delivery_minutes | 2,541 |
| Blank age | 61 |
| Age outside 10–100 | 6 |
| Distinct raw city spellings | 24 |
| Distinct non-blank raw gender spellings | 10 |
| Blank gender | 30 |

### Cleaning rules

The rules were applied in the order listed.

| Table | Rule | Rows / values changed |
|---|---|---|
| customers | city: strip spaces and apply title case (6 cities remain) | 476 values |
| customers | gender: blank → unknown | 30 values |
| customers | gender: spelling mapped to male/female (M, f, MALE, …) | 920 values |
| customers | age: outside 10–100 set to missing | 6 values |
| customers | age: missing filled with the city median (groupby + transform) | 67 values |
| customers | signup_date: text → datetime | 1,200 values |
| orders | order_ts: text → datetime | 13,084 values |
| orders | exact duplicate rows removed | 119 rows |
| orders | earlier records of the same order_id removed (latest order_ts kept) | 656 rows |
| orders | order_amount: unparseable text → missing | 112 values |
| orders | order_amount: missing filled with round(price_inr × quantity × (1 − discount_pct/100), 2) | 112 values |
| orders | delivery_minutes: negative → missing | 105 values |
| orders | delivery_minutes: completed orders filled with the category median among completed orders (groupby + transform); cancelled orders left missing | 774 values |

The audit found 120 junk amounts and 106 negative delivery times in the raw data. Fewer are changed during cleaning (112 and 105) because some of those rows were removed first as duplicates or superseded records.

Results after cleaning:
- Customers: Pune 227, Delhi 210, Bengaluru 197, Chennai 191, Hyderabad 191, Mumbai 184. Female 610, male 560, unknown 30. No missing ages, and every age is between 18 and 60.
- Orders: 12,309 rows (one per order_id), of which 11,110 are completed, 1,199 cancelled and 0 pending. No missing order_amount. No missing delivery_minutes among completed orders; all 1,199 cancelled orders have it missing.
- Completed revenue: INR 2,998,668.80.

Storage: the clean tables are in `data/clean/{customers,products,orders}.csv` and in `data/instamart.db` (tables customers, products, orders). `order_ts` is stored as text `YYYY-MM-DD HH:MM:SS`.

### SQL results (sql/queries.sql, run with pd.read_sql_query)

| Query | Technique | Result |
|---|---|---|
| Q1 | WHERE then HAVING | 30 customers whose completed orders above INR 500 total more than INR 8,000 (highest: C0693, INR 13,776.55) |
| Q2 | three-table join | 30 city × category rows summing to INR 2,998,668.80; largest is Bengaluru / Electronics at INR 233,909.45 |
| Q3 | scalar subquery | 11 products priced above the average catalogue price (INR 289.32); 8 are Electronics |
| Q4 | LEFT JOIN | 25 customers with no completed order |
| Q5 | two CTEs | 550 customers spend more than the average customer total of INR 2,552.06 |
| Q6 | RANK / DENSE_RANK / ROW_NUMBER | top customer per city: Bengaluru C0082 (INR 12,856.20), Chennai C0930 (INR 10,151.40), Delhi C0291 (INR 13,742.60), Hyderabad C0743 (INR 12,730.05), Mumbai C0693 (INR 14,766.55), Pune C0426 (INR 10,377.10); 8 rows have RANK() ≠ ROW_NUMBER() |
| Q7 | running total | 183 daily rows (2025-04-01 to 2025-09-30); the last cumulative value is INR 2,998,668.80 |

Why RANK() and ROW_NUMBER() differ: customers with the same total_spend in a city get the same RANK(), but ROW_NUMBER() always gives each row a new number. From the second member of a tie onwards, the two numbers no longer match.

Q2 completed revenue in INR (the pandas `pivot_table(..., margins=True)` grand total, INR 2,998,668.80, equals the SQL total):

| City | Dairy | Electronics | Grocery | Personal Care | Snacks | Total |
|---|---|---|---|---|---|---|
| Bengaluru | 87,075.05 | 233,909.45 | 110,915.65 | 20,193.85 | 71,549.40 | 523,643.40 |
| Chennai | 78,301.80 | 195,508.80 | 93,817.45 | 27,675.40 | 68,325.70 | 463,629.15 |
| Delhi | 117,271.70 | 158,549.10 | 112,658.05 | 23,471.50 | 90,879.45 | 502,829.80 |
| Hyderabad | 83,731.00 | 228,913.10 | 109,475.40 | 24,800.05 | 81,670.35 | 528,589.90 |
| Mumbai | 75,209.85 | 214,738.40 | 78,970.15 | 38,018.00 | 72,122.10 | 479,058.50 |
| Pune | 90,349.55 | 187,629.25 | 108,456.60 | 34,275.15 | 80,207.50 | 500,918.05 |
| All | 531,938.95 | 1,219,248.10 | 614,293.30 | 168,433.95 | 464,754.50 | 2,998,668.80 |

### pandas cross-check and exploratory analysis

Completed order_amount per city (groupby with named aggregation):

| City | Sum (INR) | Mean (INR) | Count |
|---|---|---|---|
| Bengaluru | 523,643.40 | 276.47 | 1,894 |
| Chennai | 463,629.15 | 272.72 | 1,700 |
| Delhi | 502,829.80 | 243.62 | 2,064 |
| Hyderabad | 528,589.90 | 284.95 | 1,855 |
| Mumbai | 479,058.50 | 297.00 | 1,613 |
| Pune | 500,918.05 | 252.48 | 1,984 |

Statistics for completed order_amount:

| Statistic | Value |
|---|---|
| Mean | INR 269.91 |
| Median | INR 135.00 |
| Skewness | 4.61 |
| Q1 / Q3 | INR 64.80 / INR 297.00 |
| 1.5 × IQR fences | INR −283.50 / INR 645.30 |
| Outliers below / above | 0 / 897 |

Correlation (completed orders): order_amount–discount_pct −0.095, order_amount–quantity +0.087, and every other pair is below 0.013 in absolute value.

**What is this data about?** It covers 11,110 completed quick-commerce orders from April to September 2025, placed by 1,175 customers in six cities across 40 grocery, dairy, snack, personal-care and electronics products.

**What do the distributions look like?** Order value is strongly right-skewed. The mean (INR 269.91) is about twice the median (INR 135.00), the skewness is 4.61, and half of all orders fall between INR 64.80 and INR 297.00.

**Are there outliers or anomalies?** 897 orders (8.1%) are above the upper fence of INR 645.30, and none are below the lower fence. Most of these (635) are electronics purchases. They are genuine high-value baskets, not errors, so they are kept. The real anomalies (junk amounts, negative delivery times, duplicates) were fixed during cleaning.

**What relationships exist?** All correlations are weak. The largest in absolute value is order_amount with discount_pct (r = −0.095), just ahead of order_amount with quantity (+0.087). A correlation this small does not establish causation: discounts may simply fall more often on cheaper items.

## Part B

To be completed in Phase 2.

## Part C

To be completed in Phase 3.

## Part D

To be completed in Phase 4.

## Limitations and Next Steps

- The data is synthetic, so the patterns reflect the generator's assumptions rather than real customer behaviour.
- Missing ages and delivery times are filled with medians. This shrinks the variance of those columns and can hide real differences between cities or categories.
- The 897 high-value orders are kept as genuine. Any analysis of averages should report medians alongside them.
- Later Parts and their limitations are added in the next phases.
