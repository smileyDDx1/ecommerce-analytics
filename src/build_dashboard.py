"""
Build a self-contained interactive dashboard (dashboard/index.html) from the
query outputs in data/outputs/. Data is embedded directly into the HTML so the
file opens anywhere with no server — suitable for GitHub Pages or a portfolio
link. Charts use Chart.js from a CDN; the cohort heatmap is a plain HTML table.

Run (after analysis.py):
    python src/build_dashboard.py
"""
from __future__ import annotations
import json
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "outputs"
DASH = ROOT / "dashboard"
DASH.mkdir(exist_ok=True)


def csv(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / f"{name}.csv")


def main() -> None:
    insights = json.loads((OUT / "insights.json").read_text(encoding="utf-8"))
    kpis = insights["kpis"]

    monthly = csv("monthly_revenue")
    top_products = csv("top_products")
    by_country = csv("revenue_by_country").head(10)
    seg = csv("rfm_segment_summary")
    cohort = csv("cohort_retention_pct")

    payload = {
        "kpis": kpis,
        "insights": insights,
        "monthly": monthly.to_dict(orient="list"),
        "top_products": top_products.to_dict(orient="list"),
        "by_country": by_country.to_dict(orient="list"),
        "segments": seg.to_dict(orient="records"),
        "cohort": {
            "index": cohort["cohort_month"].tolist(),
            "cohort_size": cohort["cohort_size"].tolist(),
            "months": [c for c in cohort.columns if c not in ("cohort_month", "cohort_size")],
            "rows": cohort.drop(columns=["cohort_month"]).to_dict(orient="list"),
            "matrix": cohort.drop(columns=["cohort_month", "cohort_size"]).values.tolist(),
        },
    }

    html = TEMPLATE.replace("/*DATA*/", json.dumps(payload))
    (DASH / "index.html").write_text(html, encoding="utf-8")
    print(f"[dashboard] wrote {DASH / 'index.html'} ({len(html)//1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E-Commerce Revenue &amp; Retention</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#0f1420; --panel:#1a2234; --panel2:#141b2a; --ink:#e8edf6; --muted:#93a0b8;
    --line:#2a3650; --accent:#5b8cff; --accent2:#4fd1c5; --warn:#f6a609; --bad:#ef5f6b;
  }
  @media (prefers-color-scheme: light){
    :root{ --bg:#f5f7fb; --panel:#ffffff; --panel2:#f0f3f9; --ink:#17203a; --muted:#5a6680; --line:#e2e8f3; }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
  .wrap{max-width:1180px;margin:0 auto;padding:28px 16px 64px}
  header h1{margin:0 0 4px;font-size:26px}
  header p{margin:0;color:var(--muted)}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:22px 0}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
  .kpi .v{font-size:23px;font-weight:700;letter-spacing:-.3px}
  .kpi .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin-top:2px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  @media (max-width:820px){.grid{grid-template-columns:1fr}}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
  .card h2{margin:0 0 2px;font-size:16px}
  .card .sub{color:var(--muted);font-size:12.5px;margin:0 0 12px}
  .full{grid-column:1/-1}
  canvas{max-height:320px}
  table.heat{border-collapse:collapse;width:100%;font-size:12px}
  table.heat th,table.heat td{padding:5px 7px;text-align:center;border:1px solid var(--bg)}
  table.heat th{color:var(--muted);font-weight:600}
  table.heat td.lbl{text-align:left;color:var(--muted);white-space:nowrap}
  .insight{background:var(--panel2);border-left:3px solid var(--accent);border-radius:8px;padding:11px 14px;margin:9px 0;font-size:14px}
  .insight b{color:var(--accent2)}
  footer{color:var(--muted);font-size:12.5px;margin-top:26px;text-align:center}
  .tag{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:12px;color:var(--muted);margin-left:6px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>E-Commerce Revenue &amp; Retention <span class="tag" id="daterange"></span></h1>
    <p>Online Retail II · ~1M transactions · UK online retailer · 2009–2011</p>
  </header>

  <section class="kpis" id="kpis"></section>

  <section class="grid">
    <div class="card full">
      <h2>Monthly revenue &amp; average order value</h2>
      <p class="sub">Net sales by month (cancellations &amp; returns excluded)</p>
      <canvas id="revChart"></canvas>
    </div>

    <div class="card">
      <h2>Top 10 products by revenue</h2>
      <p class="sub">Net revenue per stock code</p>
      <canvas id="prodChart"></canvas>
    </div>

    <div class="card">
      <h2>Revenue by country (top 10)</h2>
      <p class="sub">Identified-customer revenue</p>
      <canvas id="countryChart"></canvas>
    </div>

    <div class="card">
      <h2>RFM segments — revenue</h2>
      <p class="sub">Customers bucketed by Recency / Frequency / Monetary quartiles</p>
      <canvas id="segChart"></canvas>
    </div>

    <div class="card">
      <h2>RFM segments — customers</h2>
      <p class="sub">How many customers fall in each segment</p>
      <canvas id="segCustChart"></canvas>
    </div>

    <div class="card full">
      <h2>Cohort retention</h2>
      <p class="sub">% of each first-purchase cohort still buying in later months (month 0 = 100%)</p>
      <div style="overflow-x:auto"><table class="heat" id="cohort"></table></div>
    </div>

    <div class="card full">
      <h2>Key insights</h2>
      <div id="insights"></div>
    </div>
  </section>

  <footer>
    Built with Python (pandas) · SQL (PostgreSQL / SQLite) · Chart.js ·
    data: UCI Online Retail II #502. Figures computed from the full dataset by <code>src/analysis.py</code>.
  </footer>
</div>

<script>
const D = /*DATA*/;
const css = k => getComputedStyle(document.documentElement).getPropertyValue(k).trim();
const money = n => '£' + Number(n).toLocaleString('en-GB',{maximumFractionDigits:0});
const k = D.kpis;

document.getElementById('daterange').textContent =
  (D.monthly.month[0]||'') + ' → ' + (D.monthly.month[D.monthly.month.length-1]||'');

const kpiDefs = [
  ['Total revenue', money(k.total_revenue)],
  ['Orders', Number(k.total_orders).toLocaleString()],
  ['Customers', Number(k.total_customers).toLocaleString()],
  ['Avg order value', '£'+Number(k.avg_order_value).toFixed(2)],
  ['Returns rate', k.returns_rate_pct+'%'],
  ['Repeat-purchase rate', D.insights.repeat_purchase_rate_pct+'%'],
];
document.getElementById('kpis').innerHTML = kpiDefs.map(
  ([l,v])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');

Chart.defaults.color = css('--muted');
Chart.defaults.borderColor = css('--line');
Chart.defaults.font.family = 'system-ui,sans-serif';
const PAL = ['#5b8cff','#4fd1c5','#f6a609','#ef5f6b','#a78bfa','#38bdf8','#fb7185','#34d399','#fbbf24','#818cf8'];

new Chart(revChart,{data:{labels:D.monthly.month,
  datasets:[
    {type:'line',label:'Revenue',data:D.monthly.revenue,borderColor:css('--accent'),backgroundColor:'rgba(91,140,255,.15)',fill:true,tension:.3,yAxisID:'y'},
    {type:'line',label:'Avg order value',data:D.monthly.avg_order_value,borderColor:css('--accent2'),tension:.3,yAxisID:'y1'}
  ]},
  options:{responsive:true,interaction:{mode:'index',intersect:false},
    scales:{y:{title:{display:true,text:'Revenue (£)'}},
            y1:{position:'right',grid:{drawOnChartArea:false},title:{display:true,text:'AOV (£)'}}}}});

new Chart(prodChart,{type:'bar',
  data:{labels:D.top_products.description.map(s=>s.length>22?s.slice(0,22)+'…':s),
    datasets:[{data:D.top_products.revenue,backgroundColor:css('--accent')}]},
  options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{title:{display:true,text:'Revenue (£)'}}}}});

new Chart(countryChart,{type:'bar',
  data:{labels:D.by_country.country,datasets:[{data:D.by_country.revenue,backgroundColor:css('--accent2')}]},
  options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{title:{display:true,text:'Revenue (£)'}}}}});

new Chart(segChart,{type:'bar',
  data:{labels:D.segments.map(s=>s.segment),datasets:[{data:D.segments.map(s=>s.total_revenue),backgroundColor:PAL}]},
  options:{plugins:{legend:{display:false}},scales:{y:{title:{display:true,text:'Revenue (£)'}}}}});

new Chart(segCustChart,{type:'doughnut',
  data:{labels:D.segments.map(s=>s.segment),datasets:[{data:D.segments.map(s=>s.customers),backgroundColor:PAL}]},
  options:{plugins:{legend:{position:'right'}}}});

// Cohort heatmap
(function(){
  const t=document.getElementById('cohort'), months=D.cohort.months, M=D.cohort.matrix;
  let h='<tr><th class="lbl">Cohort</th><th>Size</th>'+months.map(m=>`<th>M${m}</th>`).join('')+'</tr>';
  D.cohort.index.forEach((label,i)=>{
    h+=`<tr><td class="lbl">${label}</td><td>${D.cohort.cohort_size[i]}</td>`;
    M[i].forEach(v=>{
      if(v===null||v===undefined||Number.isNaN(v)){h+='<td></td>';return;}
      const a=Math.min(v/60,1);
      h+=`<td style="background:rgba(91,140,255,${a.toFixed(3)});color:${a>0.5?'#fff':'var(--ink)'}">${v}%</td>`;
    });
    h+='</tr>';
  });
  t.innerHTML=h;
})();

// Insights
const I=D.insights, S=Object.fromEntries(I.segments.map(s=>[s.segment,s]));
const lines=[
  `Repeat-purchase rate is <b>${I.repeat_purchase_rate_pct}%</b> — most customers buy only once, so retention is the growth lever, not acquisition.`,
  `<b>Champions</b> are a small cohort but drive <b>${I.champions_share_of_revenue_pct}%</b> of revenue — protect them.`,
  `<b>At-Risk</b> customers hold <b>${I.at_risk_share_of_revenue_pct}%</b> of revenue — the priority win-back segment.`,
  I.avg_month1_retention_pct!=null?`Average month-1 retention is <b>${I.avg_month1_retention_pct}%</b> across cohorts.`:null,
  `Returns run at <b>${k.returns_rate_pct}%</b> of gross revenue.`,
  I.top_country_after_uk?`Largest market after the UK is <b>${I.top_country_after_uk}</b>.`:null,
].filter(Boolean);
document.getElementById('insights').innerHTML=lines.map(x=>`<div class="insight">${x}</div>`).join('');
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
