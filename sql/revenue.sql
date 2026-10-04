-- ============================================================================
-- Core revenue queries.  Each block is tagged `-- @name: <output>`; the runner
-- (src/analysis.py) executes each block and writes data/outputs/<output>.csv.
--
-- Engine note: written for the bundled SQLite demo DB. The only non-portable
-- piece is the month bucket; the PostgreSQL form is given beside each use:
--   SQLite:    strftime('%Y-%m', invoice_date)
--   Postgres:  to_char(invoice_date, 'YYYY-MM')
-- All sales figures exclude cancellations (is_cancelled) and returns (revenue<=0).
-- ============================================================================

-- @name: monthly_revenue
-- Revenue trend by calendar month, with order volume and average order value.
WITH order_rev AS (
    SELECT i.invoice_no,
           strftime('%Y-%m', i.invoice_date) AS ym,   -- Postgres: to_char(i.invoice_date,'YYYY-MM')
           SUM(it.revenue)                   AS order_revenue
    FROM invoices i
    JOIN invoice_items it USING (invoice_no)
    WHERE i.is_cancelled = 0 AND it.revenue > 0
    GROUP BY i.invoice_no, ym
)
SELECT ym                                   AS month,
       ROUND(SUM(order_revenue), 2)         AS revenue,
       COUNT(*)                             AS orders,
       ROUND(SUM(order_revenue) / COUNT(*), 2) AS avg_order_value
FROM order_rev
GROUP BY ym
ORDER BY ym;

-- @name: top_products
-- Top 10 products by net revenue.
SELECT p.stock_code,
       p.description,
       ROUND(SUM(it.revenue), 2) AS revenue,
       SUM(it.quantity)          AS units_sold
FROM invoice_items it
JOIN invoices i USING (invoice_no)
JOIN products p USING (stock_code)
WHERE i.is_cancelled = 0 AND it.revenue > 0
GROUP BY p.stock_code, p.description
ORDER BY revenue DESC
LIMIT 10;

-- @name: revenue_by_country
-- Revenue, orders and customer count by country (identified customers).
SELECT c.country,
       ROUND(SUM(it.revenue), 2)          AS revenue,
       COUNT(DISTINCT i.invoice_no)       AS orders,
       COUNT(DISTINCT i.customer_id)      AS customers
FROM invoices i
JOIN invoice_items it USING (invoice_no)
JOIN customers c       USING (customer_id)
WHERE i.is_cancelled = 0 AND it.revenue > 0
GROUP BY c.country
ORDER BY revenue DESC;

-- @name: kpis
-- Headline KPIs for the dashboard scorecards.
WITH sales AS (
    SELECT it.revenue, i.invoice_no, i.customer_id
    FROM invoices i JOIN invoice_items it USING (invoice_no)
    WHERE i.is_cancelled = 0 AND it.revenue > 0
),
returns AS (
    SELECT SUM(ABS(it.revenue)) AS return_value
    FROM invoices i JOIN invoice_items it USING (invoice_no)
    WHERE it.revenue < 0
)
SELECT ROUND(SUM(s.revenue), 2)                                   AS total_revenue,
       COUNT(DISTINCT s.invoice_no)                               AS total_orders,
       COUNT(DISTINCT s.customer_id)                              AS total_customers,
       ROUND(SUM(s.revenue) / COUNT(DISTINCT s.invoice_no), 2)    AS avg_order_value,
       ROUND((SELECT return_value FROM returns) * 100.0
             / ((SELECT return_value FROM returns) + SUM(s.revenue)), 2) AS returns_rate_pct
FROM sales s;
