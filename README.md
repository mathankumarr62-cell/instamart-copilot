# Instamart Customer Intelligence & Support Copilot

## Overview

The Instamart Customer Intelligence & Support Copilot is an internal tool for the (fictional, synthetic) Swiggy Instamart customer-experience team. It turns dirty raw exports into a trusted database: INR 2,998,668.80 of completed revenue across 11,110 orders. It splits 1,175 customers into four actionable segments and predicts which of them will stop ordering (38.32% of the cohort lapsed in September). It triages 164 support tickets without leaking personal data to the model, sending every fraud ticket to the security team. Finally, it answers policy questions from the policy documents only and runs a refund agent that refunds automatically up to INR 1000, escalates larger amounts and never pays the same order twice. Everything runs offline with the Python standard library, pandas, numpy, scikit-learn and joblib. Every language-model call goes through the supplied `mock_llm.py`, so no API key or network connection is needed. All money is in INR.

### Results at a glance

Every row is asserted by `python validate.py`, which checks 179 gating checkpoints and ends with `ALL CHECKPOINTS PASSED`. "Ours" values come from `outputs/reports/part_<x>.json`.

| Checkpoint | Reference (brief) | Ours | Match |
|---|---|---|---|
| Clean orders: rows / completed / cancelled / pending | 12,309 / 11,110 / 1,199 / 0 | 12,309 / 11,110 / 1,199 / 0 | yes |
| Completed revenue | INR 2,998,668.80 | INR 2,998,668.80 | yes |
| Q2 largest city × category cell | Bengaluru / Electronics, INR 233,909 | Bengaluru / Electronics, INR 233,909.45 | yes |
| Q5 customers above the average spend | 550; average INR 2,552.06 | 550; average INR 2,552.06 | yes |
| Q6 rows with RANK() ≠ ROW_NUMBER() | 8 | 8 | yes |
| Q7 daily rows / last cumulative value | 183 / INR 2,998,668.80 | 183 / INR 2,998,668.80 | yes |
| RFM customers / recency median | 1,175 / 19 | 1,175 / 19 | yes |
| K = 4 inertia / silhouette | 743.1 / 0.526 (±5%, ±0.05) | 743.1 / 0.526 | yes |
| PCA explained variance (2 components) | about 0.634 + 0.218 = 0.852 (±0.02) | 0.634 + 0.218 = 0.852 | yes |
| Lapse cohort / lapsed | 1,156 / 443 (38.32%) | 1,156 / 443 (38.32%) | yes |
| Baseline "never lapsed" accuracy / F1 | 61.6% / 0 | 61.6% / 0 | yes |
| Logistic regression best C / test F1 | C = 1 / about 0.62 ("of this order") | C = 100 / 0.648 | of this order (see Part B) |
| Random forest best params / test F1 | depth 8, leaf 10 / about 0.65 (selected ≥ 0.55) | depth 8, leaf 10 / 0.652 | yes |
| Oversampling: recall / precision | about 0.64 → 0.85 / stays near 0.6 | 0.652 → 0.854 / 0.644 → 0.589 | yes |
| PII redacted: emails / phones / order ids / left | 55 / 91 / 132 / 0 | 55 / 91 / 132 / 0 | yes |
| Statuses: classified_json / keyword / invalid | 135 / 12 / 9 | 135 / 12 / 9 | yes |
| Zero-shot accuracy (fraud→billing, technical→billing) | 85.7% (11, 10) | 85.7% (11, 10) | yes |
| Few-shot accuracy | 100% | 100.0% | yes |
| Policy chunks (40 words, overlap 10) | 15 | 15 | yes |
| RAG evaluation: doc in top 3 / fact in answer / fallback | 12/12, 12/12, 2/2 | 12/12, 12/12, 2/2 | yes |
| Agent S1 to S7 outcomes | REFUND 128.25, REFUND 135.00, ESCALATE 1999.00, DENIED, DENIED, NOT_FOUND, FALLBACK | same | yes |
| S1 model calls | 5 | 5 | yes |
| Stop safely: S7 / token_limit 200 / time_limit 0 | MAX_ITERATIONS / TOKEN_LIMIT / TIMEOUT fallbacks | FALLBACK_MAX_ITERATIONS / FALLBACK_TOKEN_LIMIT / FALLBACK_TIMEOUT | yes |
| Crash and resume tools / result | get_order, search_policy, calculate_refund, issue_refund / REFUND 128.25 | same | yes |

### Architecture

```
 generate_data.py ──► data/raw/  (customers, products, orders, tickets, policies, eval + scenarios)
                         │
                         ▼
 Part A  audit ─► clean ─► SQLite data/instamart.db ─► SQL Q1-Q7 + pandas EDA
                         │ data/clean/*.csv
                         ▼
 Part B  RFM ─► K-means segments ─► customer_segments.csv
          └──► lapse features (orders before 2025-09-01) ─► tuned models ─► lapse_model.joblib, retention_list.csv
                         │ segment / Premium flag
                         ▼
 Part C  ticket ─► guardrails ─► PII redaction ─► mock_llm (retries) ─► validator ─► route ─► triage_results.csv
                         │
                         ▼
 Part D  policies ─► 40-word chunks ─► TF-IDF ─► grounded answers (mock_llm)
          refund agent (ReAct, 5 tools, 3 limits) ─► agent_runs.jsonl, refund_ledger.jsonl, state/ checkpoints

 Every part ─► outputs/reports/part_<x>.json ─► validate.py, README and the optional dashboard (app/)
```

### Repository structure

```
generate_data.py, mock_llm.py   supplied files, unmodified
requirements.txt                pip freeze of the pinned environment
part_a.py ... part_d.py         thin entry scripts, one per part
run_all.py                      runs Parts A-D in order, one summary line per part
validate.py                     asserts every reference checkpoint
sql/queries.sql                 Part A queries Q1-Q7
src/instamart/
  config.py                     every path and constant (pathlib, relative to the repo root)
  part_a/ ... part_d/           one module per responsibility (cleaning, rfm, triage, agent, ...)
  checkpoints.py, validation.py the shared checkpoint list and Check machinery
  llm_backend.py                the single import point for mock_llm.py
  dashboard/                    read-only views, live demos and the HTTP handler for app/
app/server.py, app/static/      optional dashboard (standard library + plain HTML/CSS/JS)
tests/                          unittest suites for every part and the dashboard
outputs/                        committed graded outputs and reports/part_<x>.json
state/                          agent checkpoints (state/demo/ is the gitignored dashboard sandbox)
```

### Dashboard (optional)

After the Reproduce steps, run `python app/server.py` and open http://127.0.0.1:8000 (stop it with Ctrl+C; `--port` picks another port). It has nine sections: Overview with the live checkpoint table, Data Quality, SQL Insights, Customer Segments with a customer lookup, Lapse Risk, Support Triage with "Try a ticket", Policy Assistant, Refund Agent with live runs and traces, and About. The server uses only the standard library, binds to 127.0.0.1, and only reads the graded outputs. Its live agent demos write to `state/demo/` and never to `outputs/`. The API has `GET /api/overview`, `/api/part-a` to `/api/part-d`, `/api/customers/<id>`, and `POST /api/triage/try`, `/api/policy/ask`, `/api/agent/run` and `/api/agent/reset`.

## Reproduce

Requires Python 3.11 or newer. The pinned versions publish wheels for Python 3.11 to 3.14, and every checkpoint was verified from a clean clone on Python 3.12.10 and 3.14. Run from the repository root:

1. `python -m venv .venv`
2. Activate it: `.venv\Scripts\Activate.ps1` (Windows PowerShell), `.venv\Scripts\activate.bat` (cmd) or `source .venv/bin/activate` (macOS/Linux)
3. `python -m pip install -r requirements.txt`
4. `python generate_data.py`
5. `python run_all.py`
6. `python validate.py`

Step 4 ends with `generated: customers=1200 products=40 orders_raw=13084 tickets=164`. Step 5 prints one summary line per part. Step 6 ends with `ALL CHECKPOINTS PASSED`. Optional: `python -m unittest discover tests` runs the unit tests. `python part_a.py` to `python part_d.py` run single parts in order. Re-running Part D rewrites `outputs/agent_runs.jsonl`, `outputs/refund_ledger.jsonl` and `state/*.json`; only the ledger timestamps change.

## Part A

**So what:** INR 2,998,668.80 of completed revenue from 11,110 orders is now trustworthy, after removing 775 duplicate or superseded order rows and repairing 120 junk amounts and 106 negative delivery times.

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

Why RANK() and ROW_NUMBER() differ: customers with the same total_spend in a city share one RANK(), while ROW_NUMBER() always gives each row a new number, so from the second member of a tie onwards the two numbers no longer match.

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

**So what:** 443 of 1,156 customers (38.32%) stopped ordering in September, and the cohort had spent INR 2,204.54 each on average in the five months before. The selected random forest catches 58 of the 89 lapsers in the test set, and the 138 Premium Big Spenders (INR 7,129.70 average spend) get their own retention list.

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

**Why inertia can't choose K on its own:** inertia is the sum of squared distances from each customer to its nearest centroid, and adding centroids can only keep that sum the same or make it smaller, so K=8 always beats K=2 and K=1,175 would reach zero. A falling inertia therefore rewards over-splitting rather than revealing real structure. It has to be read for its elbow and weighed against silhouette and against whether the business can act on the segments.

### Segment profiles (K = 4)

| segment_id | Name | Size | Mean recency (days) | Mean frequency | Mean monetary (INR) | Premium | Recommended action |
|---|---|---|---|---|---|---|---|
| 1 | Premium Big Spenders | 138 | 24.1 | 6.8 | 7,129.70 | yes | Assign a priority support line and early access to new electronics launches |
| 2 | Loyal Regulars | 419 | 8.8 | 19.4 | 3,410.02 | no | Reward with a subscription-style loyalty pass to protect their weekly basket |
| 0 | Occasional Shoppers | 436 | 28.9 | 3.8 | 1,057.62 | no | Nudge a second monthly order with a free-delivery threshold reminder |
| 3 | Dormant / Lapsing | 182 | 109.0 | 2.2 | 685.99 | no | Send a time-limited win-back coupon on their favourite grocery staples |

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

**So what:** all 34 fraud tickets reach the security team at HIGH priority and 11 Premium tickets reach the premium desk. The 17 tickets the pipeline cannot handle safely go to humans, and no email, phone number or order id ever reaches the model.

`part_c.py` triages the 164 tickets in `data/raw/tickets.csv` in file order (read with `keep_default_na=False`), using `mock_llm.py` for every model call and `mock_llm.est_tokens` for every token count. Code: `src/instamart/part_c/` (guardrails, redaction, prompts, llm_client, validation, triage, routing). All numbers below come from `outputs/reports/part_c.json`.

### Input guardrails and redaction

| Check | Result |
|---|---|
| Empty or whitespace-only tickets (`skipped_empty`, never sent) | 4 |
| Tickets above MAX_INPUT_TOKENS = 400 (`flagged_long`, never sent) | 4, each 734 estimated tokens |
| Tickets eligible for the model | 156 |
| Emails replaced by `[EMAIL]` | 55 |
| Phone numbers replaced by `[PHONE]` | 91 |
| Order ids replaced by `[ORDER_ID]` | 132 |
| Total substitutions (all 164 tickets) | 278 |
| Pattern matches after re-applying the three patterns to the redacted texts | 0 |

The patterns run in the order email, phone, order id. The user message is exactly the redacted ticket text. `assert_no_pii` runs right before every `chat` call (retries included) and fails if any message still matches a pattern.

### Retries

Each model call is wrapped in `call_with_retry`. It allows at most 3 retries per ticket on `TransientLLMError`. The wait before retry n is 0.05 × 2**n × uniform(0.9, 1.15) seconds, using a jitter generator seeded with 42. `mock_llm.reset()` is called right before each full run. Every full run over the 156 eligible tickets hit **19 TransientLLMErrors, all recovered on retry 0**, with no permanent error. Waits ranged from 0.0453 to 0.0562 s, inside the 0.045 to 0.0575 s band. Sample log lines:

```
INFO instamart.part_c.llm_client: retry ticket=T0002 retry=0 wait=0.0530s after 503 server busy
INFO instamart.part_c.llm_client: retry ticket=T0116 retry=0 wait=0.0453s after 503 server busy
INFO instamart.part_c.llm_client: retry ticket=T0153 retry=0 wait=0.0484s after 503 server busy
```

### Output validation

Each reply is parsed with `json.loads`. It is accepted when `category` is one of billing, delivery, technical or fraud (`classified_json`). A reply that is not JSON is split into words with `re.findall(r"[a-z]+", text.lower())` and accepted only if exactly one category word appears (`classified_keyword`). This catches the mock's "billing-related" style answers. Everything else is `flagged_invalid_output`, including JSON with the unknown category "shipping". Nothing is guessed.

| Status (one full run) | Tickets |
|---|---|
| classified_json | 135 |
| classified_keyword | 12 |
| flagged_invalid_output | 9 |
| skipped_empty | 4 |
| flagged_long | 4 |

### Zero-shot versus few-shot (no budget)

The zero-shot system prompt is 26 estimated tokens. The few-shot prompt is 103: the same instructions, an `EXAMPLES:` line and four labelled examples, one of them fraud.

| Prompt | Classified | Correct | Accuracy | Total tokens | Tokens per classified ticket |
|---|---|---|---|---|---|
| Zero-shot | 147 | 126 | 85.7% | 8,464 | 57.6 |
| Few-shot | 147 | 147 | 100.0% | 20,476 | 139.3 |

Zero-shot confusion table (rows = true category, columns = predicted; classified tickets only):

| true \ predicted | billing | delivery | technical | fraud |
|---|---|---|---|---|
| billing | 38 | 0 | 0 | 0 |
| delivery | 0 | 36 | 0 | 0 |
| technical | 10 | 0 | 29 | 0 |
| fraud | 11 | 0 | 0 | 23 |

The few-shot prompt costs 12,012 extra tokens per run, 2.4 times as many (81.7 more tokens per classified ticket). It fixes all 21 zero-shot errors, about 572 extra tokens per corrected ticket. The errors are not random: 11 of the 34 classified fraud tickets were labelled billing. Those tickets would sit in the normal support queue instead of reaching the security team within the escalation policy's 2 hours. That risk makes the few-shot tokens worth paying for here. The zero-shot prompt would be enough only for a low-stakes pre-sort where a human re-checks every billing ticket anyway.

### Budget demo and final routing

**Budget demo** (`outputs/triage_budget_demo.csv`): a zero-shot run with TOKEN_BUDGET = 6000 used 6,027 tokens over 111 model calls. Before each call it checks whether the running total is already at or above the budget. **45 tickets ended `budget_exhausted`** and were routed to human review. The 6000 budget did not need lowering.

**Final run** (`outputs/triage_results.csv`, 164 rows): a few-shot run with TOKEN_BUDGET = 100000, with no ticket exhausted. Routing reads `outputs/customer_segments.csv` from Part B; a customer with no segment row would count as not premium, though every ticket's customer has one.

| Route | Priority | Tickets |
|---|---|---|
| support_queue | NORMAL | 102 |
| security_team (fraud) | HIGH | 34 |
| human_review | NORMAL | 17 |
| premium_desk (Premium Big Spenders) | HIGH | 11 |

**Rule-validated vs sent to humans.** The 147 classified tickets (135 by JSON parsing, 12 by the single-keyword rule) passed the rule-based validator and were routed automatically. The 17 human-review tickets never received an automatic category: 4 empty, 4 too long (never sent to the model) and 9 whose replies failed validation. In the budget demo, the 45 `budget_exhausted` tickets also went to humans. The validator only checks that a reply is well formed and uses an allowed category; it cannot tell whether the category is correct. The zero-shot run shows this: all 21 wrong labels passed validation.

## Part D

**So what:** policy answers come from the right document for 12 of 12 test questions. Refunds are automated only up to INR 1000: S1 and S2 were refunded INR 128.25 and INR 135.00, S3's INR 1,999.00 went to a human, and a crashed run resumes without paying twice.

`part_d.py` builds the policy assistant and runs the refund agent. Code: `src/instamart/part_d/` (chunking, retrieval, rag, evaluation, tools, agent, checkpoint). Every model call goes through `mock_llm.chat`. Numbers come from `outputs/reports/part_d.json`. A full run first clears `outputs/agent_runs.jsonl`, `outputs/refund_ledger.jsonl` and the `state/*.json` checkpoints, so re-runs reproduce the same files (only ledger timestamps change).

### Chunking and retrieval

Each document is split on whitespace into 40-word chunks that start 30 words apart (overlap 10), stopping after the first chunk that reaches the last word. Each chunk records its source file.

| Source | Chunks (overlap 10) | Chunks (overlap 0) |
|---|---|---|
| refund_policy.txt | 4 | 3 |
| delivery_policy.txt | 3 | 3 |
| escalation_policy.txt | 3 | 2 |
| payment_policy.txt | 3 | 3 |
| privacy_policy.txt | 2 | 2 |
| **Total** | **15** | **13** |

`TfidfVectorizer()` is fitted on the chunk texts, a query is transformed with the same vectorizer, and `retrieve(query, k=3)` ranks chunks by `cosine_similarity`. It returns `{source, score, text}`. For "refund policy late delivery", the top three are all `refund_policy.txt` (scores 0.2719, 0.2514, 0.2454).

**TF-IDF in two sentences.** TF (term frequency) measures how often a word appears in a chunk, so a chunk that keeps saying "refund" scores high for "refund". IDF (inverse document frequency) down-weights words that appear in many chunks, such as "order" or "customer", so rare and specific words like "wallet" or "OTP" decide the ranking. **Limitation:** TF-IDF only matches exact word forms. "money back" or "reimbursement" share no terms with a chunk that says "refund", so a question phrased with synonyms can retrieve nothing relevant even though the answer exists.

### Grounded answers and evaluation

`answer(question)` retrieves three chunks and sends two messages. The system message contains `POLICY ASSISTANT` and tells the model to answer only from the context, or say it could not find the information. The user message is `CONTEXT:\n` + each chunk as `[<source>]\n<text>` + `\nQUESTION:\n` + the question. The function returns the text and the three sources.

| Metric (`data/raw/policy_eval.csv`) | Overlap 10 | Overlap 0 |
|---|---|---|
| Answerable: expected_doc in top 3 | 12/12 | 12/12 |
| Answerable: expected_fact in answer (case-sensitive) | 12/12 | 10/12 |
| Unanswerable: answer begins "I could not find" | 2/2 | 2/2 |

**Why overlap 0 breaks.** Both failures are sentences cut in half at the 40-word chunk boundary:

- *"What delivery time makes a completed order eligible for a full refund?"* The refund chunk ends with "If a completed order is delivered in more than 45 minutes, the customer" and the next chunk starts "receives a full refund of the order amount." The words "full refund" from the question are in the second half, so the model answers "receives a full refund of the order amount.", which lacks "more than 45 minutes". With overlap 10, the whole sentence sits in one chunk.
- *"How soon is money returned when a payment fails but is deducted?"* The payment chunk ends at "the amount is returned automatically". The words "within 48 hours" open the next chunk, which is not in the top three, so the answer lacks "48 hours".

### Tools

`TOOLS_SPEC` lists five tools, each with a name, a one-sentence description and JSON-schema-style parameters. `TOOL_MAP` maps each name to its function, and `execute_tool` looks the name up and calls it with the model's argument dictionary. Unknown tools or bad arguments become `{"error": ...}` observations.

| Tool | Behaviour |
|---|---|
| `get_order(order_id)` | Reads `data/instamart.db` and returns `{order_id, status, order_amount, delivery_minutes}` (`null` minutes for undelivered orders) or `{"error": "order not found"}` |
| `search_policy(query)` | `{"results": retrieve(query)}` |
| `calculate_refund(order_amount, delivery_minutes)` | Completed and delivered in **more than 45 minutes** gives 100% of order_amount, otherwise 0, rounded to 2 decimals (45 min gives INR 0, 46 min gives the full amount) |
| `issue_refund(order_id, refund_inr)` | Appends `{timestamp, tool, order_id, refund_inr, run_id}` to `outputs/refund_ledger.jsonl` and returns `{"refund_inr"}`. As a second guard, it refuses amounts above INR 1000 (INR 1000 is issued, INR 1000.01 is refused) |
| `escalate_to_human(order_id, refund_inr)` | Same ledger line, for a human lead to approve |

Both ledger tools are idempotent per order: if `refund_ledger.jsonl` already holds a line for the same `order_id` and tool, they append nothing and return the recorded `{"refund_inr"}` with `"duplicate_prevented": true`, so a retried or resumed run can never pay or escalate the same order twice.

### Refund agent (ReAct, default limits: 6 iterations, 6,000 tokens, 10 s)

`run_agent` starts from a system message containing `AGENT` and the user message. It appends `{"role": "assistant", "content": None, "tool_calls": [{id, name, arguments}]}` and `{"role": "tool", "tool_call_id", "name", "content": <JSON string>}` for every tool step. The status is the word before the colon in the final answer. Each run appends one line to `outputs/agent_runs.jsonl`, holding every step's tool, arguments and observation.

| Scenario | Status | Refund (INR) | Model calls | Tokens | Tools executed |
|---|---|---|---|---|---|
| S1 | REFUND | 128.25 | 5 | 1,122 | get_order, search_policy, calculate_refund, issue_refund |
| S2 | REFUND | 135.00 | 5 | 1,122 | get_order, search_policy, calculate_refund, issue_refund |
| S3 | ESCALATE | 1999.00 | 5 | 1,109 | get_order, search_policy, calculate_refund, escalate_to_human |
| S4 | DENIED | 0.00 | 4 | 785 | get_order, search_policy, calculate_refund (delivered in 45 minutes or less) |
| S5 | DENIED | 0.00 | 3 | 472 | get_order, search_policy (order not completed) |
| S6 | NOT_FOUND | 0.00 | 2 | 162 | get_order |
| S7 | FALLBACK_MAX_ITERATIONS | 0.00 | 6 | 3,270 | search_policy × 6 |

S7 made all six model calls well under the 6,000-token limit. The ledger holds exactly three lines: S1's and S2's issued refunds and S3's escalation. The crash-and-resume demo re-runs S1's order, so its `issue_refund` returns `duplicate_prevented: true` and adds no line.

### Stopping safely

The loop enforces three limits:

- At the top of each iteration it stops with `FALLBACK_TIMEOUT` once `time.monotonic()` shows that `time_limit_seconds` or more have passed.
- It stops with `FALLBACK_MAX_ITERATIONS` after `max_iterations` model calls without a final answer.
- After each call it adds `usage.total_tokens`. If the total is over `token_limit`, it stops with `FALLBACK_TOKEN_LIMIT` *before* running the requested tool.

Every fallback returns the steps so far and a handoff summary (the reason, calls, tokens, tools run and the original request).

| Demonstration | Status | Model calls | Tokens | Tools executed |
|---|---|---|---|---|
| S7, default limits | **FALLBACK_MAX_ITERATIONS** | 6 | 3,270 | search_policy × 6 |
| S1 with token_limit = 200 | **FALLBACK_TOKEN_LIMIT** | 3 | 489 | get_order, search_policy (the requested calculate_refund was not run) |
| S1 with time_limit_seconds = 0 | **FALLBACK_TIMEOUT** | 0 | 0 | none (stopped before the first model call) |

### Crash and resume

After every tool observation, the agent writes `state/<run_id>.json` atomically. The file holds the run id, scenario id, full message list, tokens used, model calls, step number, the tools already executed and the steps. `resume_agent(run_id)` loads it and continues the same loop. Model calls and tokens carry over; the wall clock restarts.

Demo with S1 (run id `S1_crash_resume`): a `SimulatedCrash` is raised right after the second tool's checkpoint is saved, then `resume_agent` is called.

| Phase | Tools executed, in order | Model calls |
|---|---|---|
| Before the crash | 1. get_order, 2. search_policy | 2 |
| After resume | 3. calculate_refund, 4. issue_refund | 3 |
| **Overall** | **get_order, search_policy, calculate_refund, issue_refund** (4 executions, none repeated) | 5 |

The resumed run ends with **REFUND, INR 128.25**, the same result as the uninterrupted S1 run. Because S1 already refunded ORD-100048, the resumed `issue_refund` is a prevented duplicate and the ledger keeps one line for that order.

### ReAct versus plan-and-execute

My ReAct agent calls the model once per step and resends the growing history each time. That cost S1 5 calls and 1,122 tokens, S4 4 calls, S5 3 calls and 472 tokens, S6 2 calls and 162 tokens. Plan-and-execute asks once for the full step list (get_order, search_policy, calculate_refund, issue_refund) and runs it without the model. The happy path then needs about 2 calls (plan plus final answer), and tokens drop sharply because observations are not resent on every call.

That saving disappears on the unexpected branches, which make up 4 of my 7 scenarios. If S6 returns "order not found", or S5's order is cancelled, a fixed plan would carry on into calculate_refund with missing or ineligible data. The executor must notice the error and replan, which costs a third call and still risks acting on stale assumptions. ReAct simply stops early: S6 finishes in 2 calls and S5 in 3, fewer than the planned path. The refund amount also decides between issue_refund and escalate_to_human, and only observation-driven reasoning picks that correctly without a replan.

For this refund workflow I would keep ReAct. Each step depends on the last observation and the money-moving step must follow a verified calculation. Running about 1,100 tokens per request is cheap, and the iteration, token and time limits, plus the ledger guard against issuing over INR 1000, bound the extra cost and risk. Plan-and-execute fits long, predictable pipelines better.

## Limitations and Next Steps

- **Synthetic data.** The data comes from `generate_data.py`, so the patterns reflect the generator's assumptions, not real customer behaviour. Missing ages and delivery times are filled with medians, which shrinks the variance of those columns and can hide real differences between cities or categories. The 897 high-value orders are kept as genuine, so any analysis of averages should report medians alongside them.
- **Post-hoc Premium label.** The Premium flag used for the retention list is a post-hoc whole-window label: it comes from RFM over the full window, which includes the September lapse window. The retention list is therefore illustrative and not a leakage-free evaluation. A production version would segment customers on pre-cutoff data only.
- **One split, fixed threshold.** The lapse model uses one 5-month history, one 30-day label window and one random split. Its decision threshold is fixed at 0.5, where a cost-weighted threshold (the value of a retained customer against the cost of a coupon) would suit the retention budget better.
- **Mock LLM.** Every model call goes to a deterministic keyword mock. The 100% few-shot accuracy says the prompt carries the right signal for this mock, not that a real model would reach it. The validator checks the format, not the truth: wrong but well-formed categories pass, so a sample of automatically routed tickets should still be audited. The refund agent follows the mock's scripted reasoning. Its safety comes from the deterministic tools (the refund rule and the INR 1000 guard in `issue_refund`) and the three limits, not from the model.
- **Redaction coverage.** The patterns cover only the three formats in the brief. Names, addresses, card numbers, and phone numbers written with spaces or a +91 prefix would pass through unredacted.
- **TF-IDF synonym limits.** Retrieval matches exact words only, so "money back" or "reimbursement" will not match a chunk that says "refund". Fixed 40-word chunks also cut sentences, as the overlap-0 run shows.
- **With real data I would:**
  - validate the cleaning rules against source-system documentation;
  - build segments and features from pre-cutoff data only, and evaluate with rolling time-based backtests over several cutoffs;
  - calibrate probabilities and choose the threshold from campaign economics;
  - put a real LLM behind the same guardrails, validator and retry wrapper, then measure accuracy and cost on a labelled ticket sample;
  - add NER-based PII detection;
  - replace TF-IDF with sentence-aware chunking plus embedding or hybrid retrieval, evaluated on a larger question set;
  - move the refund ledger into a transactional database with a unique key per order and action.
