-- Part A SQL analysis against data/instamart.db.
-- Unless stated otherwise only completed orders count as revenue or spend. All money is INR.

-- Q1: WHERE then HAVING - customers whose completed orders above INR 500 total more than INR 8000
SELECT customer_id,
       COUNT(*)                    AS big_orders,
       ROUND(SUM(order_amount), 2) AS total_big_orders_inr
FROM orders
WHERE status = 'completed' AND order_amount > 500
GROUP BY customer_id
HAVING SUM(order_amount) > 8000
ORDER BY total_big_orders_inr DESC;

-- Q2: three-table join - completed revenue by city and product category
SELECT c.city,
       p.category,
       ROUND(SUM(o.order_amount), 2) AS revenue_inr
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN products  p ON p.product_id  = o.product_id
WHERE o.status = 'completed'
GROUP BY c.city, p.category
ORDER BY revenue_inr DESC;

-- Q3: scalar subquery - products priced above the average catalogue price
SELECT product_id, product_name, category, price_inr
FROM products
WHERE price_inr > (SELECT AVG(price_inr) FROM products)
ORDER BY price_inr DESC;

-- Q4: LEFT JOIN - customers who have no completed order
SELECT c.customer_id, c.city
FROM customers c
LEFT JOIN orders o
       ON o.customer_id = c.customer_id AND o.status = 'completed'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;

-- Q5: common table expressions - customers whose completed spend is above the average customer total
WITH customer_spend AS (
    SELECT customer_id, SUM(order_amount) AS total_spend
    FROM orders
    WHERE status = 'completed'
    GROUP BY customer_id
),
average_spend AS (
    SELECT AVG(total_spend) AS avg_spend FROM customer_spend
)
SELECT s.customer_id,
       ROUND(s.total_spend, 2) AS total_spend_inr,
       ROUND(a.avg_spend, 2)   AS avg_spend_inr
FROM customer_spend s
CROSS JOIN average_spend a
WHERE s.total_spend > a.avg_spend
ORDER BY s.total_spend DESC;

-- Q6: ranking window functions - RANK, DENSE_RANK and ROW_NUMBER of customer spend within each city
WITH customer_spend AS (
    SELECT c.city, o.customer_id, ROUND(SUM(o.order_amount), 2) AS total_spend
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.status = 'completed'
    GROUP BY c.city, o.customer_id
)
SELECT city,
       customer_id,
       total_spend,
       RANK()       OVER (PARTITION BY city ORDER BY total_spend DESC) AS rnk,
       DENSE_RANK() OVER (PARTITION BY city ORDER BY total_spend DESC) AS dense_rnk,
       ROW_NUMBER() OVER (PARTITION BY city ORDER BY total_spend DESC) AS row_num
FROM customer_spend
ORDER BY city, row_num;

-- Q7: running total - daily completed revenue with a cumulative revenue column
WITH daily AS (
    SELECT SUBSTR(order_ts, 1, 10) AS day, SUM(order_amount) AS revenue
    FROM orders
    WHERE status = 'completed'
    GROUP BY day
)
SELECT day,
       ROUND(revenue, 2)                             AS revenue_inr,
       ROUND(SUM(revenue) OVER (ORDER BY day), 2)    AS cumulative_revenue_inr
FROM daily
ORDER BY day;
