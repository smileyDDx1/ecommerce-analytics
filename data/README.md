# Data

The raw dataset is **not** committed (it is ~45 MB and gitignored). Download it once:

**Online Retail II** — UCI Machine Learning Repository, dataset #502
<https://archive.ics.uci.edu/dataset/502/online+retail+ii>

```bash
# from the repo root
python -c "import urllib.request; urllib.request.urlretrieve('https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip', 'data/online_retail_II.zip')"
```

`src/etl.py` unzips it automatically on first run. It is ~1,067,000 transaction
rows across two Excel sheets (2009–2010 and 2010–2011), one UK online retailer.

Columns: `Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer ID, Country`.

Generated files that also live here (all gitignored):
- `online_retail_II.xlsx` — extracted from the zip by the ETL
- `ecommerce.db` — the SQLite demo database the pipeline builds
- `outputs/` — query result CSVs + `etl_summary.json` + `insights.json`
