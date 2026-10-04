"""
Run the SQL analysis files against the database and write result CSVs to
data/outputs/. Also derives the cohort-retention percentage matrix (pivot of
cohort_counts) and a compact insights.json the README/dashboard read from.

Run (after etl.py):
    python src/analysis.py
"""
from __future__ import annotations
import json
import os
import pathlib
import re

import pandas as pd
from sqlalchemy import create_engine

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "outputs"
SQL = ROOT / "sql"
OUT.mkdir(parents=True, exist_ok=True)

DB_URL = os.environ.get("DATABASE_URL", f"sqlite:///{(DATA / 'ecommerce.db').as_posix()}")
engine = create_engine(DB_URL)

BLOCK_RE = re.compile(r"--\s*@name:\s*(\w+)\s*\n(.*?)(?=\n--\s*@name:|\Z)", re.S)


def run_file(path: pathlib.Path) -> dict[str, pd.DataFrame]:
    """Execute each `-- @name:` block in a .sql file; return {name: dataframe}."""
    text = path.read_text(encoding="utf-8")
    results: dict[str, pd.DataFrame] = {}
    for name, body in BLOCK_RE.findall(text):
        sql = body.strip().rstrip(";")
        df = pd.read_sql_query(sql, engine)
        df.to_csv(OUT / f"{name}.csv", index=False)
        results[name] = df
        print(f"[analysis] {name}: {len(df)} rows -> outputs/{name}.csv")
    return results


def build_cohort_matrix(cohort_counts: pd.DataFrame) -> pd.DataFrame:
    """Pivot the long cohort counts into a retention-% matrix (month_index 0 = 100%)."""
    wide = cohort_counts.pivot(index="cohort_month", columns="month_index", values="customers")
    sizes = wide[0]
    pct = wide.div(sizes, axis=0).mul(100).round(1)
    pct.insert(0, "cohort_size", sizes.astype(int))
    pct.to_csv(OUT / "cohort_retention_pct.csv")
    return pct


def main() -> None:
    res: dict[str, pd.DataFrame] = {}
    for f in ("revenue.sql", "rfm.sql", "cohorts.sql"):
        res.update(run_file(SQL / f))

    cohort_pct = build_cohort_matrix(res["cohort_counts"])

    # --- derive headline insights from the real results -------------------
    kpis = res["kpis"].iloc[0].to_dict()
    seg = res["rfm_segment_summary"]
    total_rev = float(kpis["total_revenue"])

    champions = seg.loc[seg["segment"] == "Champions"]
    at_risk = seg.loc[seg["segment"] == "At-Risk"]

    # Month-2 retention: mean of month_index==1 across cohorts with a full window.
    m1 = cohort_pct[1].dropna()
    repeat_rate = round(
        (res["rfm_segments"]["frequency"] > 1).mean() * 100, 1
    )

    insights = {
        "kpis": {k: float(v) for k, v in kpis.items()},
        "repeat_purchase_rate_pct": repeat_rate,
        "avg_month1_retention_pct": round(float(m1.mean()), 1) if len(m1) else None,
        "segments": seg.to_dict(orient="records"),
        "champions_share_of_revenue_pct": round(float(champions["total_revenue"].sum()) / total_rev * 100, 1)
        if len(champions) else 0.0,
        "at_risk_share_of_revenue_pct": round(float(at_risk["total_revenue"].sum()) / total_rev * 100, 1)
        if len(at_risk) else 0.0,
        "top_country_after_uk": res["revenue_by_country"].iloc[1]["country"]
        if len(res["revenue_by_country"]) > 1 else None,
    }
    (OUT / "insights.json").write_text(json.dumps(insights, indent=2), encoding="utf-8")

    print("\n===== HEADLINE NUMBERS =====")
    print(f"Total revenue (sales)      : {kpis['total_revenue']:,.0f}")
    print(f"Orders / Customers         : {int(kpis['total_orders']):,} / {int(kpis['total_customers']):,}")
    print(f"Avg order value            : {kpis['avg_order_value']:,.2f}")
    print(f"Returns rate               : {kpis['returns_rate_pct']}%")
    print(f"Repeat-purchase rate       : {repeat_rate}%")
    print(f"Avg month-1 retention      : {insights['avg_month1_retention_pct']}%")
    print(f"Champions share of revenue : {insights['champions_share_of_revenue_pct']}%")
    print(f"At-Risk share of revenue   : {insights['at_risk_share_of_revenue_pct']}%")
    print("Segments:")
    print(seg.to_string(index=False))


if __name__ == "__main__":
    main()
