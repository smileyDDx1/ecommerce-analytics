# E-Commerce Revenue & Customer Retention Analytics

End-to-end analytics on **~1.07M real retail transactions**: a Python ETL that
cleans messy transactional data into a normalised SQL schema, SQL analysis using
joins and window functions (monthly revenue, RFM segmentation, cohort retention),
and an interactive dashboard that turns the numbers into decisions.

**Dataset:** [Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii)
(UCI #502) — one UK online retailer, Dec 2009 – Dec 2011.

> **Live dashboard:** _add your GitHub Pages / Tableau Public link here_ ·
> see [`dashboard/index.html`](dashboard/index.html) (self-contained, opens in any browser)

---

## Key insights

Computed from the full dataset by `src/analysis.py` — numbers below are the real output, not placeholders.

1. **Retention is the lever, not acquisition.** The repeat-purchase rate is **72%**, but
   average **month-1 cohort retention is only ~21%** — buyers come back, yet most lapse quickly
   after the first month. Re-engagement in weeks 2–6 is where the money is.
2. **Revenue is dangerously concentrated.** **Champions** — 761 customers (13% of the base) —
   drive **47% of all revenue** (£9.5M of £20.5M). A handful of accounts leaving would hurt badly;
   they warrant white-glove retention.
3. **At-Risk customers are the priority win-back.** 888 customers holding **11% of revenue** (£2.2M)
   haven't ordered in ~275 days on average. They were valuable (avg 6.5 orders) and are slipping — the
   highest-ROI segment to target.
4. **The business is UK-first by a wide margin.** The UK is **£14.4M of £20.5M** (~70%); the next
   markets are **EIRE, Netherlands, Germany, France**. International is a small, high-AOV long tail.
5. **Returns run at ~7.3%** of gross revenue, and **235k rows (£2.9M of activity) have no Customer ID** —
   a data-capture gap worth closing, since those sales can't be attributed to any customer or cohort.

---

## Tech stack

| Layer | Tool |
|---|---|
| ETL / cleaning | Python, pandas |
| Database | **PostgreSQL** (schema + queries); a bundled **SQLite** demo DB runs it with zero setup |
| Analysis | SQL — CTEs, window functions (`NTILE`), joins |
| Dashboard | Chart.js (self-contained HTML) — reproducible in Tableau Public from the same CSVs |

Why SQLite *and* Postgres: [`sql/schema.sql`](sql/schema.sql) is dialect-neutral DDL that runs on both,
and the pipeline loads whichever `DATABASE_URL` points at. SQLite is the default so a reviewer can run
the whole thing with no database server. The analysis queries are standard SQL; the only engine-specific
piece (a date difference, a month bucket) is noted inline with its Postgres equivalent.

## How to run

```bash
pip install -r requirements.txt

# 1. fetch the raw data (~45 MB, one time) — see data/README.md
python -c "import urllib.request; urllib.request.urlretrieve('https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip','data/online_retail_II.zip')"

# 2. clean + load into the database (SQLite by default)
python src/etl.py
#    …or against PostgreSQL:
#    DATABASE_URL=postgresql+psycopg2://user:pass@localhost/retail python src/etl.py

# 3. run the SQL analysis -> data/outputs/*.csv + insights.json
python src/analysis.py

# 4. build the dashboard -> dashboard/index.html
python src/build_dashboard.py
```

## Data model

A small star-style schema rather than one flat table ([`sql/schema.sql`](sql/schema.sql)):

```
customers (customer_id PK, country)         products (stock_code PK, description)
        \                                      /
         invoices (invoice_no PK, customer_id FK, invoice_date, is_cancelled)
                               |
         invoice_items (item_id PK, invoice_no FK, stock_code FK, quantity, price, revenue)
```

`is_cancelled` flags the dataset's "C"-prefixed cancellations so returns stay analysable instead of
being dropped. `customer_id` is nullable: rows without a Customer ID still count toward revenue/product
totals, but the customer-level analyses (RFM, cohort) filter them out.

## How the cleaning handles the real-world quirks

| Quirk | Handling | This run |
|---|---|---|
| Exact duplicate rows | dropped | 34,335 removed |
| Cancellations (`Invoice` starts `C`) | flagged `is_cancelled`, kept for returns analysis | 8,292 invoices |
| Negative quantities / returns | flagged `is_return`; excluded from sales, counted for returns rate | 22,497 lines |
| Missing Customer ID | kept for revenue totals, excluded from RFM/cohort | 235,151 rows (£2.9M) |
| Missing key (invoice/date/code) | dropped | 0 |

Every count is written to `data/outputs/etl_summary.json`, so the funnel from 1,067,371 raw rows to
1,033,036 clean line-items is fully auditable.

## What's inside

```
ecommerce-analytics/
├── README.md
├── requirements.txt
├── data/            # raw file gitignored; download note in data/README.md
│   └── outputs/     # query-result CSVs + etl_summary.json + insights.json
├── src/
│   ├── etl.py             # load + clean + load into the DB (Postgres or SQLite)
│   ├── analysis.py        # runs sql/*.sql, writes CSVs + insights.json
│   └── build_dashboard.py # renders dashboard/index.html from the outputs
├── sql/
│   ├── schema.sql    # normalised schema (runs on Postgres and SQLite)
│   ├── revenue.sql   # monthly revenue, top products, revenue by country, KPIs
│   ├── rfm.sql       # RFM segmentation via NTILE window functions
│   └── cohorts.sql   # monthly cohort retention
└── dashboard/
    └── index.html    # interactive dashboard (self-contained)
```

## Methodology notes

- **RFM:** per customer, Recency (days since last order), Frequency (distinct orders), Monetary (total
  revenue); each bucketed into quartiles with `NTILE(4)` (4 = best); segments labelled from the R/F
  scores (Champions, Loyal, At-Risk, Lost, New/Promising). See [`sql/rfm.sql`](sql/rfm.sql).
- **Cohort retention:** customers grouped by first-purchase month; for each later month, the share of
  that cohort who ordered again. Month 0 = 100% baseline. See [`sql/cohorts.sql`](sql/cohorts.sql).
- **Reproducing in Tableau Public:** connect to the Postgres DB (or load `data/outputs/*.csv`), then
  build revenue-over-time, top products/countries, the RFM segment breakdown, and a cohort heatmap from
  `cohort_retention_pct.csv`. The bundled `dashboard/index.html` mirrors that layout.
