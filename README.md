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
5. `python part_a.py` (clean, store, query: writes data/clean, data/instamart.db, outputs/reports/part_a.json)
6. `python part_b.py` (segments and lapse model: writes outputs/customer_segments.csv, lapse_model.joblib, retention_list.csv, reports/part_b.json)
7. `python -m unittest`
8. `python validate.py` (last line: `ALL CHECKPOINTS PASSED`)

`python run_all.py` runs steps 5 and 6 in one go.

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

All customer behaviour comes from completed orders in `data/clean/orders.csv`, combined with `data/clean/customers.csv`.

### RFM table (snapshot 2025-10-01 00:00:00)

| Metric | Value |
|---|---|
| Customers with at least one completed order | 1,175 |
| Recency (days): median / min / max | 19 / 0 / 180 |
| Frequency (orders): mean / max | 9.46 / 33 |
| Monetary (INR): mean / max | 2,552.06 / 14,766.55 |

### K-means on standardised R, F, M (n_init=10, random_state=42)

| K | Inertia | Silhouette |
|---|---|---|
| 2 | 1820.8 | 0.465 |
| 3 | 1268.2 | 0.445 |
| 4 | 743.1 | **0.526** |
| 5 | 617.4 | 0.480 |
| 6 | 503.2 | 0.482 |
| 7 | 408.5 | 0.416 |
| 8 | 366.5 | 0.412 |

**Chosen K = 4.** The elbow is at K=4: going from 3 to 4 clusters cuts inertia by 41%, and each later step saves only 10–19%. K=4 also has the best silhouette score (0.526). Its four groups map directly onto four distinct campaigns.

**Why inertia can't choose K on its own:** inertia is the sum of squared distances from each customer to its nearest centroid. Adding centroids can only keep that sum the same or make it smaller, so K=8 always beats K=2, and K=1,175 would reach zero. A falling inertia therefore rewards over-splitting. It has to be read for its elbow and weighed against silhouette and against whether the business can act on the segments.

### Segment profiles (K = 4)

| segment_id | Name | Size | Mean recency (days) | Mean frequency | Mean monetary (INR) | Premium | Recommended action |
|---|---|---|---|---|---|---|---|
| 1 | Premium Big Spenders | 138 | 24.1 | 6.8 | 7,129.70 | yes | Priority support line and early access to new electronics launches |
| 2 | Loyal Regulars | 419 | 8.8 | 19.4 | 3,410.02 | no | Subscription-style loyalty pass to protect the weekly basket |
| 0 | Occasional Shoppers | 436 | 28.9 | 3.8 | 1,057.62 | no | Nudge a second monthly order with a free-delivery threshold reminder |
| 3 | Dormant / Lapsing | 182 | 109.0 | 2.2 | 685.99 | no | Time-limited win-back coupon on favourite grocery staples |

The names come from the profile values, not from cluster numbers:
- The segment with the highest mean monetary value is **Premium** (`is_premium`).
- Of the rest, the one with the highest mean recency is Dormant, and the one with the highest frequency is Loyal.

Cluster numbers are arbitrary labels with no order. Segment 1 is not "better" than segment 0, and the numbers can change if the data or the library version changes.

PCA (2 components) on the scaled RFM matrix explains 0.634 + 0.218 = **0.852** of the variance. The segments are written to `outputs/customer_segments.csv`.

### Lapse problem

The cutoff is 2025-09-01. A customer is `lapsed` = 1 if they have no completed order from 2025-09-01 to 2025-09-30.

The features are built only from orders dated before the cutoff, plus the clean customer table:
- recency (days before the cutoff), frequency and monetary
- average discount_pct and average delivery_minutes of completed orders
- cancellation rate (cancelled orders ÷ all orders with a final status)
- favourite category (ties broken alphabetically), city, age, gender, and tenure_days (cutoff − signup_date)

| Item | Value |
|---|---|
| Cohort (at least one completed order before the cutoff) | 1,156 customers |
| Lapsed | 443 (38.32%) |
| Train / test split (stratified, random_state=42) | 924 / 232 (354 / 89 lapsed) |
| Missing feature values | 0 (checked in code) |
| Baseline "never lapsed" on test | accuracy 61.6%, lapsed-class precision / recall / F1 = 0 / 0 / 0 |

**Leakage controls:**
- No encoder, scaler or resampler saw a test row. `OneHotEncoder(drop="first", handle_unknown="ignore")` for city, gender and favourite category, and `StandardScaler` for the numeric features, sit inside one scikit-learn `Pipeline` that is fitted on training rows only. Oversampling touches only the training set.
- No data from 2025-09-01 onwards entered the features. A unit test confirms that adding orders on or after the cutoff leaves the features unchanged.
- The segment labels from Part B task 3 were not used as features.

**Scaler check:** the fitted scaler's mean of frequency is 8.1147, against 8.0285 for the full cohort. They differ because the scaler learned only from the 924 training rows, so the 232 test customers had no influence on it.

### Tuning (GridSearchCV, cv=5, scoring="f1", training rows only)

| Model | Grid | Best parameters | Best CV F1 |
|---|---|---|---|
| LogisticRegression(max_iter=1000) | C ∈ {0.01, 0.1, 1, 10, 100} (25 fits) | C = 100 | 0.651 |
| RandomForestClassifier(n_estimators=100, random_state=42) | max_depth ∈ {3, 5, 8} × min_samples_leaf ∈ {5, 10, 20} (45 fits) | max_depth = 8, min_samples_leaf = 10 | 0.682 |

The logistic-regression CV curve is flat: C = 0.1 / 1 / 10 / 100 score 0.646 / 0.645 / 0.649 / 0.651, all within one fold standard deviation (about 0.03). The brief's reference picks C = 1. Our best C depends only on how ties in favourite category are broken, and the test F1 stays of the same order as the reference.

### Test-set evaluation (after tuning, lapsed class = positive)

| Model | Confusion matrix [[TN, FP], [FN, TP]] | Precision | Recall | F1 |
|---|---|---|---|---|
| Baseline (never lapsed) | [[143, 0], [89, 0]] | 0.000 | 0.000 | 0.000 |
| Logistic regression (C=100) | [[111, 32], [31, 58]] | 0.644 | 0.652 | 0.648 |
| Random forest (depth 8, leaf 10) | [[112, 31], [31, 58]] | 0.652 | 0.652 | **0.652** |

**Model choice: the random forest.** For Instamart, missing a lapsing customer is the costlier error: that customer's future baskets are lost, and the cohort spent INR 2,204.54 on average in the five months before the cutoff. Wrongly targeting a loyal customer costs only a coupon's margin. The two models catch exactly the same 58 of 89 lapsers, so they tie on the expensive error. The forest makes one fewer wasted offer and has the highest test F1 (0.652, well above the 0.55 floor). It also captures non-linear effects, such as high spend combined with few orders, without manual interaction terms.

### Class-balance experiment (oversampling the training set only)

All 924 training rows are kept. 216 lapsed rows are drawn with replacement (random_state=42), giving 570 rows per class. The best logistic regression is then refitted and evaluated on the original test set.

| Logistic regression | Precision | Recall | F1 |
|---|---|---|---|
| Unbalanced training | 0.644 | 0.652 | 0.648 |
| Oversampled to 570 / 570 | 0.589 | **0.854** | 0.697 |

**Recall moved the most (+0.20).** The balanced model finds 76 of 89 lapsers instead of 58, while precision falls slightly rather than rising: 53 loyal customers are wrongly flagged instead of 32. For the retention team, this means a wider net that catches most at-risk customers. Given the cost asymmetry, that is usually worth the extra coupons.

### Interpretation

Top 5 random-forest importances:

| Feature | Importance | Business reading |
|---|---|---|
| frequency | 0.307 | Ordering habit is the strongest signal: customers with many past orders keep ordering |
| monetary | 0.247 | Spend level separates low-value one-off buyers from established customers |
| recency | 0.115 | A long gap before the cutoff is an early warning of churn |
| cancellation_rate | 0.062 | Customers with more cancelled orders behave differently |
| avg_discount_pct | 0.058 | How much a customer depends on discounts shifts their lapse risk |

Logistic-regression coefficient signs (on scaled features):

| Feature | Coefficient | Business reading |
|---|---|---|
| frequency | −1.70 | More past orders mean much lower lapse odds, so protecting the habit protects revenue |
| recency | +0.04 | A longer silence before the cutoff means slightly higher lapse odds (small, because frequency already captures most of it) |
| monetary | +0.28 | At the same number of orders, higher spend means higher lapse odds: big-ticket one-off buyers leave after their purchase |

### Persistence and retention list

The random forest pipeline is saved with `joblib.dump` to `outputs/lapse_model.joblib`. When reloaded with `joblib.load`, it reproduces the original 232 test predictions exactly. This is asserted in code and re-checked by `validate.py`.

The cohort's test set contains 40 Premium customers. `outputs/retention_list.csv` holds the 10 with the highest predicted lapse probability (0.4497 to 0.5025). **0 of these 10 actually lapsed.** Premium customers lapse less often than the cohort overall (31.9% vs 38.3%), and only one of them (C0060, 0.5025) is above the 0.5 decision threshold. The 12 Premium test customers who did lapse are ranked lower, which is another sign that this list is not a reliable evaluation.

The Premium flag comes from the whole-window RFM, which includes the September window that defines the lapse label. That makes it a post-hoc label, so this retention list is illustrative and not a leakage-free evaluation.

## Part C

To be completed in Phase 3.

## Part D

To be completed in Phase 4.

## Limitations and Next Steps

- The data is synthetic, so the patterns reflect the generator's assumptions rather than real customer behaviour.
- Missing ages and delivery times are filled with medians. This shrinks the variance of those columns and can hide real differences between cities or categories.
- The 897 high-value orders are kept as genuine. Any analysis of averages should report medians alongside them.
- The Premium flag used for the retention list is a post-hoc whole-window label: it comes from RFM over the full window, including the September lapse window. The retention list is therefore illustrative and not a leakage-free evaluation. A production version would segment customers on pre-cutoff data only.
- The lapse model uses a single 5-month history and one 30-day label window. A rolling, time-based validation over several cutoffs would give a more honest error estimate than one random split.
- The decision threshold is fixed at 0.5. A cost-weighted threshold, using the value of a retained customer and the cost of a coupon, would suit the retention budget better.
- Later Parts and their limitations are added in the next phases.
