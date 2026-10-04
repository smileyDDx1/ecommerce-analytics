-- ============================================================================
-- Monthly cohort retention.
--
-- Each customer belongs to the cohort of their first-purchase month. For every
-- later month we count how many of that cohort bought again. month_index = 0 is
-- the acquisition month (the cohort's 100% baseline).
--
-- Engine note — month arithmetic:
--   SQLite:    strftime('%Y', d) / strftime('%m', d)  (used below)
--   Postgres:  EXTRACT(YEAR FROM d) / EXTRACT(MONTH FROM d),
--              or date_trunc('month', d) for the cohort label.
-- Identified customers only; sales only (cancellations excluded).
-- ============================================================================

-- @name: cohort_counts
WITH first_purchase AS (
    SELECT customer_id, MIN(invoice_date) AS first_dt
    FROM invoices
    WHERE is_cancelled = 0 AND customer_id IS NOT NULL
    GROUP BY customer_id
),
activity AS (
    SELECT DISTINCT
        fp.customer_id,
        strftime('%Y-%m', fp.first_dt) AS cohort_month,
        ( (CAST(strftime('%Y', i.invoice_date) AS INTEGER) * 12 + CAST(strftime('%m', i.invoice_date) AS INTEGER))
        - (CAST(strftime('%Y', fp.first_dt)      AS INTEGER) * 12 + CAST(strftime('%m', fp.first_dt)      AS INTEGER))
        ) AS month_index
    FROM invoices i
    JOIN first_purchase fp USING (customer_id)
    WHERE i.is_cancelled = 0
)
SELECT cohort_month,
       month_index,
       COUNT(DISTINCT customer_id) AS customers
FROM activity
GROUP BY cohort_month, month_index
ORDER BY cohort_month, month_index;
