"""
ETL for the Online Retail II dataset.

Pipeline:  raw .xlsx (2 sheets)  ->  clean  ->  normalised star schema  ->  DB

Run:
    python src/etl.py                      # loads the bundled SQLite demo DB
    DATABASE_URL=postgresql+psycopg2://user:pass@localhost/retail python src/etl.py

The same code loads PostgreSQL or SQLite — SQLAlchemy abstracts the engine and
schema.sql is dialect-neutral. Every cleaning decision is counted and written to
data/outputs/etl_summary.json so the funnel from raw rows to loaded rows is
auditable rather than a black box.
"""
from __future__ import annotations
import json
import os
import pathlib
import sys
import time
import zipfile

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

ZIP = DATA / "online_retail_II.zip"
XLSX = DATA / "online_retail_II.xlsx"
DB_URL = os.environ.get("DATABASE_URL", f"sqlite:///{(DATA / 'ecommerce.db').as_posix()}")


def log(msg: str) -> None:
    print(f"[etl] {msg}", flush=True)


def load_raw() -> pd.DataFrame:
    """Read both worksheets and concatenate into one frame."""
    if not XLSX.exists():
        if not ZIP.exists():
            sys.exit(f"Raw data not found. Expected {ZIP} or {XLSX}. See data/README.md.")
        log(f"extracting {ZIP.name}")
        with zipfile.ZipFile(ZIP) as z:
            inner = next(n for n in z.namelist() if n.lower().endswith(".xlsx"))
            with z.open(inner) as src, open(XLSX, "wb") as dst:
                dst.write(src.read())
    cache = DATA / "_raw_cache.pkl"
    if cache.exists():
        log("reading cached raw frame (_raw_cache.pkl)")
        return pd.read_pickle(cache)
    log(f"reading {XLSX.name} (both sheets — this is the slow step)")
    xls = pd.ExcelFile(XLSX)
    frames = [pd.read_excel(xls, sheet_name=s) for s in xls.sheet_names]
    df = pd.concat(frames, ignore_index=True)
    log(f"raw rows: {len(df):,} across {len(xls.sheet_names)} sheets")
    df.to_pickle(cache)
    return df


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Clean per documented real-world quirks; return cleaned rows + a summary."""
    summary: dict = {"raw_rows": int(len(df))}

    # Normalise column names: "Customer ID" -> "customer_id", etc.
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df = df.rename(columns={"invoicedate": "invoice_date", "stockcode": "stock_code"})

    # Trim whitespace on the text keys.
    for col in ("invoice", "stock_code", "description", "country"):
        df[col] = df[col].astype("string").str.strip()

    # Parse dates.
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")

    # Quirk 1: exact duplicate rows (same everything) -> keep one.
    before = len(df)
    df = df.drop_duplicates()
    summary["exact_duplicates_removed"] = before - len(df)

    # Quirk 2: rows with no usable key (missing invoice / stock_code / date).
    before = len(df)
    df = df.dropna(subset=["invoice", "stock_code", "invoice_date"])
    summary["rows_missing_key_removed"] = before - len(df)

    # Derived flags/measures.
    df["is_cancelled"] = df["invoice"].str.startswith("C").fillna(False)
    df["revenue"] = (df["quantity"] * df["price"]).round(2)

    # Quirk 3: cancellations (C-prefix) and negative quantities = returns.
    df["is_return"] = df["is_cancelled"] | (df["quantity"] < 0)
    summary["cancellation_invoices"] = int(df.loc[df["is_cancelled"], "invoice"].nunique())
    summary["return_lines"] = int(df["is_return"].sum())

    # Quirk 4: missing Customer ID (~1/4 of rows). We KEEP these for
    # revenue/product/country/returns totals (they are real sales) and null the
    # FK; the customer-level analyses (RFM, cohort) filter them out instead.
    df["customer_id"] = df["customer_id"].astype("Float64").astype("Int64")
    summary["rows_without_customer_id"] = int(df["customer_id"].isna().sum())
    summary["revenue_without_customer_id"] = float(
        df.loc[df["customer_id"].isna() & ~df["is_return"], "revenue"].sum().round(2)
    )

    df["description"] = df["description"].fillna("UNKNOWN")
    summary["clean_rows"] = int(len(df))
    summary["gross_revenue_all_rows"] = float(df["revenue"].sum().round(2))
    summary["date_min"] = str(df["invoice_date"].min())
    summary["date_max"] = str(df["invoice_date"].max())
    return df, summary


def build_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split the flat cleaned frame into the four normalised tables."""
    # customers: one row per non-null customer; country = that customer's modal country.
    cust = df.dropna(subset=["customer_id"])
    customers = (
        cust.groupby("customer_id")["country"]
        .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0])
        .reset_index()
    )

    # products: one row per stock_code; description = modal description.
    products = (
        df.groupby("stock_code")["description"]
        .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "UNKNOWN")
        .reset_index()
    )

    # invoices: one row per invoice (order grain).
    invoices = (
        df.groupby("invoice")
        .agg(
            customer_id=("customer_id", "first"),
            invoice_date=("invoice_date", "min"),
            is_cancelled=("is_cancelled", "max"),
        )
        .reset_index()
        .rename(columns={"invoice": "invoice_no"})
    )
    invoices["is_cancelled"] = invoices["is_cancelled"].astype(bool)

    # invoice_items: one row per source line, with a supplied surrogate key.
    items = df[["invoice", "stock_code", "quantity", "price", "revenue"]].copy()
    items = items.rename(columns={"invoice": "invoice_no"}).reset_index(drop=True)
    items.insert(0, "item_id", items.index + 1)

    return {
        "customers": customers,
        "products": products,
        "invoices": invoices,
        "invoice_items": items,
    }


def load(tables: dict[str, pd.DataFrame]) -> None:
    engine = create_engine(DB_URL)
    is_sqlite = engine.dialect.name == "sqlite"
    log(f"target DB: {engine.dialect.name}")

    schema_sql = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        if is_sqlite:
            conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        for raw_stmt in schema_sql.split(";"):
            # Strip line comments so a statement preceded by a `-- ...` block
            # is not mistaken for a comment and skipped.
            body = "\n".join(
                ln for ln in raw_stmt.splitlines() if not ln.strip().startswith("--")
            ).strip()
            if body:
                conn.exec_driver_sql(body)
    log("schema created from sql/schema.sql")

    # Load parents before children so the foreign keys validate on insert.
    for name in ("customers", "products", "invoices", "invoice_items"):
        t = tables[name]
        t.to_sql(name, engine, if_exists="append", index=False, chunksize=20_000)
        log(f"loaded {name}: {len(t):,} rows")


def main() -> None:
    t0 = time.time()
    df, summary = clean(load_raw())
    tables = build_tables(df)
    summary["table_row_counts"] = {k: int(len(v)) for k, v in tables.items()}
    load(tables)
    summary["db_url"] = DB_URL.split("://")[0] + "://…"
    summary["elapsed_seconds"] = round(time.time() - t0, 1)
    (OUT / "etl_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"done in {summary['elapsed_seconds']}s — summary -> data/outputs/etl_summary.json")
    for k, v in summary.items():
        if k != "table_row_counts":
            print(f"      {k}: {v}")


if __name__ == "__main__":
    main()
