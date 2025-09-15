# query_vds.py  — SUM(Sales), SUM(Profit), AVG(Discount) by State/Province (Top 10 by Profit)
import os, requests, json
from dotenv import load_dotenv
from langchain_tableau.utilities.auth import jwt_connected_app

load_dotenv()

auth = jwt_connected_app(
    jwt_client_id=os.environ['TABLEAU_JWT_CLIENT_ID'],
    jwt_secret_id=os.environ['TABLEAU_JWT_SECRET_ID'],
    jwt_secret=os.environ['TABLEAU_JWT_SECRET'],
    tableau_api=os.environ.get('TABLEAU_API_VERSION','3.21'),
    tableau_user=os.environ['TABLEAU_USER'],
    tableau_domain=os.environ['TABLEAU_DOMAIN'],
    tableau_site=os.environ['TABLEAU_SITE'],
    scopes=["tableau:content:read","tableau:viz_data_service:read"],
)
token  = auth['credentials']['token']
domain = os.environ['TABLEAU_DOMAIN']
luid   = os.environ['DATASOURCE_LUID']

# Use captions EXACTLY as returned by read-metadata
CAP_STATE    = "State/Province"
CAP_SALES    = "Sales"
CAP_PROFIT   = "Profit"
CAP_DISCOUNT = "Discount"

body = {
  "datasource": {"datasourceLuid": luid},
  "query": {
    "fields": [
      { "fieldCaption": CAP_STATE },                                  # dimension
      { "fieldCaption": CAP_SALES,    "function": "SUM", "maxDecimalPlaces": 2 },
      { "fieldCaption": CAP_PROFIT,   "function": "SUM", "sortPriority": 1, "sortDirection": "DESC" },
      { "fieldCaption": CAP_DISCOUNT, "function": "AVG", "maxDecimalPlaces": 2 },
    ],
    "filters": [
      {   # Top 10 states by SUM(Profit)
        "field": { "fieldCaption": CAP_STATE },
        "filterType": "TOP",
        "howMany": 10,
        "fieldToMeasure": { "fieldCaption": CAP_PROFIT, "function": "SUM" },
        "direction": "TOP"
      }
    ]
  },
  "options": { "returnFormat": "OBJECTS", "debug": True, "disaggregate": False }
}

resp = requests.post(
  f"{domain}/api/v1/vizql-data-service/query-datasource",
  headers={"X-Tableau-Auth": token, "Content-Type":"application/json"},
  json=body
)
print("VDS query-datasource =>", resp.status_code)
print(resp.text[:2000])
resp.raise_for_status()

# Pretty-print a small table if present
data = resp.json()
try:
    cols = [c.get("caption") or c.get("fieldCaption") or c.get("name") for c in data["data"]["columns"]]
    rows = data["data"]["data"]
    print("\nTop rows:")
    print("\t".join(cols))
    for r in rows:
        print("\t".join(str(x) for x in (r if isinstance(r, list) else r.get("values", []))))
except Exception:
    pass
