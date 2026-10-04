-- ============================================================================
-- RFM customer segmentation using window functions (NTILE).
--
-- Recency, Frequency, Monetary per customer, each bucketed into quartiles
-- (4 = best), then mapped to a named segment. Identified customers only
-- (customer_id NOT NULL), sales only (no cancellations / returns).
--
-- Engine note: recency uses a day difference from the dataset's last sale date.
--   SQLite:    CAST(julianday(:snap) - julianday(MAX(i.invoice_date)) AS INTEGER)
--   Postgres:  (:snap::date - MAX(i.invoice_date)::date)
-- The runner passes the snapshot date in; the SQLite form is active below.
-- ============================================================================

-- @name: rfm_segments
WITH snapshot AS (
    SELECT MAX(invoice_date) AS snap FROM invoices WHERE is_cancelled = 0
),
rfm AS (
    SELECT i.customer_id,
           CAST(julianday((SELECT snap FROM snapshot))
                - julianday(MAX(i.invoice_date)) AS INTEGER) AS recency_days,
           COUNT(DISTINCT i.invoice_no)                      AS frequency,
           ROUND(SUM(it.revenue), 2)                         AS monetary
    FROM invoices i
    JOIN invoice_items it USING (invoice_no)
    WHERE i.is_cancelled = 0
      AND i.customer_id IS NOT NULL
      AND it.revenue > 0
    GROUP BY i.customer_id
),
scored AS (
    SELECT *,
           NTILE(4) OVER (ORDER BY recency_days DESC) AS r_score,  -- fewer days since last order = higher tile
           NTILE(4) OVER (ORDER BY frequency    ASC ) AS f_score,  -- more orders = higher tile
           NTILE(4) OVER (ORDER BY monetary     ASC ) AS m_score   -- more spend = higher tile
    FROM rfm
)
SELECT customer_id, recency_days, frequency, monetary,
       r_score, f_score, m_score,
       CASE
           WHEN r_score >= 4 AND f_score >= 4                 THEN 'Champions'
           WHEN r_score >= 3 AND f_score >= 3                 THEN 'Loyal'
           WHEN r_score >= 3 AND f_score <= 2                 THEN 'New / Promising'
           WHEN r_score <= 2 AND f_score >= 3                 THEN 'At-Risk'
           WHEN r_score <= 2 AND f_score <= 2                 THEN 'Lost'
           ELSE 'Needs Attention'
       END AS segment
FROM scored
ORDER BY monetary DESC;

-- @name: rfm_segment_summary
-- Roll the per-customer segments up to one row per segment for the dashboard.
WITH snapshot AS (
    SELECT MAX(invoice_date) AS snap FROM invoices WHERE is_cancelled = 0
),
rfm AS (
    SELECT i.customer_id,
           CAST(julianday((SELECT snap FROM snapshot))
                - julianday(MAX(i.invoice_date)) AS INTEGER) AS recency_days,
           COUNT(DISTINCT i.invoice_no)                      AS frequency,
           ROUND(SUM(it.revenue), 2)                         AS monetary
    FROM invoices i
    JOIN invoice_items it USING (invoice_no)
    WHERE i.is_cancelled = 0 AND i.customer_id IS NOT NULL AND it.revenue > 0
    GROUP BY i.customer_id
),
scored AS (
    SELECT *,
           NTILE(4) OVER (ORDER BY recency_days DESC) AS r_score,
           NTILE(4) OVER (ORDER BY frequency    ASC ) AS f_score
    FROM rfm
),
labelled AS (
    SELECT *,
           CASE
               WHEN r_score >= 4 AND f_score >= 4 THEN 'Champions'
               WHEN r_score >= 3 AND f_score >= 3 THEN 'Loyal'
               WHEN r_score >= 3 AND f_score <= 2 THEN 'New / Promising'
               WHEN r_score <= 2 AND f_score >= 3 THEN 'At-Risk'
               WHEN r_score <= 2 AND f_score <= 2 THEN 'Lost'
               ELSE 'Needs Attention'
           END AS segment
    FROM scored
)
SELECT segment,
       COUNT(*)                        AS customers,
       ROUND(SUM(monetary), 2)         AS total_revenue,
       ROUND(AVG(monetary), 2)         AS avg_revenue,
       ROUND(AVG(frequency), 2)        AS avg_frequency,
       ROUND(AVG(recency_days), 1)     AS avg_recency_days
FROM labelled
GROUP BY segment
ORDER BY total_revenue DESC;
