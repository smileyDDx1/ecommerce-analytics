-- ============================================================================
-- Schema for the E-Commerce Revenue & Retention Analytics project
-- ----------------------------------------------------------------------------
-- Target: PostgreSQL. Also runs unchanged on the bundled SQLite demo database
-- (sqlite >= 3.25) because every type/constraint token below is one SQLite
-- also accepts. The surrogate key `item_id` is supplied by the ETL rather than
-- auto-generated, so no SERIAL/AUTOINCREMENT is needed and the DDL stays
-- dialect-neutral.
--
-- Design: a small star-style schema rather than one flat table.
--   customers / products  = dimensions
--   invoices              = the order grain (one row per invoice)
--   invoice_items         = the line-item grain (one row per invoice line)
-- `country` is modelled as a customer attribute. `is_cancelled` flags the
-- dataset's "C"-prefixed cancellation invoices so returns stay analysable
-- instead of being silently dropped.
-- ============================================================================

-- Drop in child -> parent order so foreign keys never block a re-run.
DROP TABLE IF EXISTS invoice_items;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

-- Dimensions -----------------------------------------------------------------
CREATE TABLE customers (
    customer_id  BIGINT       PRIMARY KEY,
    country      TEXT         NOT NULL
);

CREATE TABLE products (
    stock_code   TEXT         PRIMARY KEY,
    description  TEXT
);

-- Order grain ----------------------------------------------------------------
CREATE TABLE invoices (
    invoice_no   TEXT         PRIMARY KEY,
    customer_id  BIGINT       REFERENCES customers(customer_id),  -- nullable: ~1/4 of rows have no Customer ID
    invoice_date TIMESTAMP    NOT NULL,
    is_cancelled BOOLEAN      NOT NULL DEFAULT FALSE
);

-- Line-item grain ------------------------------------------------------------
CREATE TABLE invoice_items (
    item_id      BIGINT        PRIMARY KEY,
    invoice_no   TEXT          NOT NULL REFERENCES invoices(invoice_no),
    stock_code   TEXT          NOT NULL REFERENCES products(stock_code),
    quantity     INTEGER       NOT NULL,
    price        NUMERIC(10,2) NOT NULL,
    revenue      NUMERIC(12,2) NOT NULL   -- quantity * price, precomputed in ETL
);

-- Indexes on the columns the analysis queries filter / join / group on.
CREATE INDEX idx_invoices_customer ON invoices(customer_id);
CREATE INDEX idx_invoices_date     ON invoices(invoice_date);
CREATE INDEX idx_items_invoice     ON invoice_items(invoice_no);
CREATE INDEX idx_items_stock       ON invoice_items(stock_code);
