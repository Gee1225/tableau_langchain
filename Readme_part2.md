# Tableau × LangChain: End-to-End Setup & Debugging Guide

> Save this as `GUIDE.md` in your project. It captures setup, configuration, direct VizQL Data Service (VDS) tests, agent usage, and fixes for the `logicalTableId` issue.

---

## 0) Prerequisites

* **macOS** with **Anaconda/conda**
* **Tableau Cloud** site (example: `https://10ax.online.tableau.com`)
* **Connected App (JWT)** with scopes:

  * `tableau:content:read`
  * `tableau:vizql_data_service:read`
* A **published datasource** (example: *Superstore Datasource*)
* **Datasource LUID** (example: `cf2bff06-c39a-4359-99ef-0c19fc1dd31b`)
* **LLM API key** (OpenAI recommended)

---

## 1) Clone & Create Environment

```bash
git clone https://github.com/Tab-SE/tableau_langchain.git
cd tableau_langchain

# Create & activate conda env
conda env create -f environment.yml
conda activate tableau_langchain
```

> In VS Code, set the interpreter to this environment (bottom-right status bar).

---

## 2) Install Dependencies

```bash
# Install project dependencies from pyproject.toml
pip install .

# (Optional) LangGraph CLI if you’ll run the server
pip install -U "langgraph-cli[inmem]"
```

Verify the installed package and import path **inside this env**:

```bash
python - <<'PY'
import importlib.metadata as im, importlib.util
print("langchain-tableau:", im.version("langchain-tableau"))
print("module path:", importlib.util.find_spec("langchain_tableau").origin)
PY
```

You should see it under:
`/opt/anaconda3/envs/tableau_langchain/lib/python3.12/site-packages/...`

---

## 3) Configure Environment Variables

Copy the template and fill it:

```bash
cp .env.template .env
```

Example `.env`:

```dotenv
# Tableau
TABLEAU_DOMAIN=https://10ax.online.tableau.com
TABLEAU_SITE=gee1225
TABLEAU_JWT_CLIENT_ID=5d36664d-ba35-40fb-a31f-8fe891e8359a
TABLEAU_JWT_SECRET_ID=...from Connected App...
TABLEAU_JWT_SECRET=...from Connected App...
TABLEAU_API_VERSION=3.21
TABLEAU_USER=georgeagyeah@yahoo.com
DATASOURCE_LUID=cf2bff06-c39a-4359-99ef-0c19fc1dd31b

# LLM
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Tooling model used by the tool’s internal prompts
TOOLING_MODEL=gpt-4o-mini

# Optional: disable LangSmith tracing (prevents 403s if unconfigured)
LANGSMITH_TRACING=false
LANGSMITH_ENDPOINT=
LANGSMITH_API_KEY=
```

**Important:**

* `TABLEAU_DOMAIN` must include `https://` and **no** `/#/site/...` suffix.
* `TABLEAU_SITE` is the short site name only (e.g., `gee1225`).
* `TABLEAU_USER` must match your exact Tableau username/email.

Load variables in your scripts:

```python
from dotenv import load_dotenv
load_dotenv()
```

---

## 4) Quick Auth & REST Smoke Test

If you hit:

* **`MissingSchema ... Invalid URL`** → add `https://` to `TABLEAU_DOMAIN`.
* **`401001 Signin Error`** → check JWT client/secret IDs, secret, site, and `TABLEAU_USER`.

Once sign-in succeeds, proceed.

---

## 5) VizQL Data Service (VDS) Metadata Check

Use the provided helper (or write a quick script) to call:

```
POST /api/v1/vizql-data-service/read-metadata
{
  "datasource": { "datasourceLuid": "<LUID>" }
}
```

You should get **200** and a JSON array under `data` like:

```json
{"data":[
  {"fieldName":"Returned","fieldCaption":"Returned","dataType":"STRING","defaultAggregation":"COUNT","logicalTableId":"Returns_...","columnClass":"COLUMN"},
  {"fieldName":"Profit Ratio","fieldCaption":"Profit Ratio","dataType":"REAL","defaultAggregation":"SUM","columnClass":"COLUMN"}
]}
```

Notes:

* **Some fields** include `logicalTableId`; **some do not**. This is normal.
* If you saw **404** with `options->returnFormat`, remove unsupported options and send the simple payload above.

---

## 6) Direct VDS Query (Known-Good Payload)

Create `query_vds.py` (minimal example):

```python
import os, json, requests
from dotenv import load_dotenv
load_dotenv()

DOMAIN = os.environ["TABLEAU_DOMAIN"]
LUID = os.environ["DATASOURCE_LUID"]
# Obtain a session token via your jwt_connected_app flow
TOKEN = os.environ.get("TABLEAU_SESSION_TOKEN")  # or pass it in however you store it

payload = {
  "fields": [
    {"fieldCaption": "State/Province"},
    {"fieldCaption": "Sales", "function": "SUM"},
    {"fieldCaption": "Profit", "function": "SUM"},
    {"fieldCaption": "Discount", "function": "AVG"}
  ],
  "filters": []
}

resp = requests.post(
  f"{DOMAIN}/api/v1/vizql-data-service/query-datasource",
  headers={"X-Tableau-Auth": TOKEN, "Content-Type": "application/json"},
  json={"datasource": {"datasourceLuid": LUID}, "query": payload},
)

print("VDS query-datasource =>", resp.status_code)
print(resp.text)
```

You should see **200** and rows like:

```json
{"data":[
 {"State/Province":"California","SUM(Sales)":457687.63,"SUM(Profit)":76381.3871,"AVG(Discount)":0.07},
 {"State/Province":"New York","SUM(Sales)":310876.27,"SUM(Profit)":74038.5486,"AVG(Discount)":0.06}
]}
```

Common **400** causes: wrong JSON shape, unknown `fieldCaption`, or invalid `function`.

---

## 7) Run the Interactive Agent

`python main.py` shows:

```
Agent Graph saved as 'graph_visualization.png' ...
Welcome to the Tableau Agent Staging Environment!
Enter a prompt or type 'exit' to end

User:
```

Paste a question, e.g.:

```
show me average discount, total sales and profits by region sorted by profit
```

If you hit:

* **429 insufficient\_quota** → confirm `OPENAI_API_KEY` (and plan), `MODEL_PROVIDER=openai`, correct env.
* **LangSmith 403** → set `LANGSMITH_TRACING=false`.

---

## 8) Fixing the `logicalTableId` Errors (Root Cause & Patches)

### Symptom

`KeyError('logicalTableId')` during tool/agent runs.

### Why it happens

The VDS metadata sometimes includes `logicalTableId` and sometimes doesn’t. Any code that does `field["logicalTableId"]` **unconditionally** will crash.

### Apply all of these fixes

#### A) Prompt schema (`vds_schema`) updates

* Allow optional `logicalTableId` on:

  * `FieldBase` (so **every** `Field` can include it)
  * each `Field` variant (no function / with function / with calculation)
  * `FilterField` (for disambiguation in filters)
* Fix `TopNFilter.required` from `["howMany, fieldToMeasure"]` → `["howMany", "fieldToMeasure"]`

> If you want a full drop-in `vds_schema` with these changes, keep the version you already pasted during debugging.

#### B) Keep `logicalTableId` in `augment_datasource_metadata`

Edit:
`.../langchain_tableau/utilities/simple_datasource_qa.py`

Replace the post-metadata block with:

```python
datasource_metadata = query_vds_metadata(
    api_key=api_key,
    url=url,
    datasource_luid=datasource_luid
)

# Normalize fields: keep logicalTableId, ensure it's always present
normalized = []
for field in datasource_metadata.get('data', []):
    f = dict(field)                 # shallow copy
    f.pop('fieldName', None)        # optional cleanup
    f.setdefault('logicalTableId', None)  # avoid KeyError downstream
    normalized.append(f)

prompt['data_model'] = normalized
```

#### C) Make JSON payload extraction tolerant

In the same file, update `get_payload`:

````python
def get_payload(output: str):
    """
    Extract a JSON object from the model output.
    Accepts:
      - ```json ... ``` fenced code blocks
      - plain JSON
      - legacy 'JSON_payload: {...}' format
    """
    s = (output or "").strip()
    import re, json

    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", s, re.IGNORECASE) \
        or re.search(r"```\s*(\{[\s\S]*?\})\s*```", s) \
        or re.search(r"(\{[\s\S]*\})", s)

    if not m and "JSON_payload" in s:
        _, tail = s.split("JSON_payload", 1)
        m = re.search(r"(\{[\s\S]*\})", tail)

    if not m:
        raise ValueError("No JSON payload found in the model output")

    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in the payload: {e}")
````

#### D) Tolerate missing LTID everywhere

Search for strict indexing and replace it with safe access:

```bash
# In your project
grep -Rn --include="*.py" "\['logicalTableId'\]" .

# In the installed package (make sure env is active)
python - <<'PY'
import os, inspect, langchain_tableau
base = os.path.dirname(inspect.getfile(langchain_tableau))
print("site-packages dir:", base)
for root, _, files in os.walk(base):
    for f in files:
        if f.endswith(".py"):
            p = os.path.join(root, f)
            try: s = open(p, 'r', encoding='utf-8').read()
            except: continue
            if "['logicalTableId']" in s:
                print(p)
PY
```

For each match, change:

```python
field["logicalTableId"]     # ❌
field.get("logicalTableId") # ✅
```

When **building** query fields/filters, include LTID **only if present**:

```python
col = {"fieldCaption": caption}
ltid = field.get("logicalTableId")
if ltid:
    col["logicalTableId"] = ltid
```

---

## 9) Quick Tests

### A) Direct tool invocation (bypasses agent planning)

```python
# quick_test.py
import os, traceback, pkgutil
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_tableau.tools.simple_datasource_qa import initialize_simple_datasource_qa

load_dotenv()
print("langchain-tableau loaded from:", pkgutil.get_loader("langchain_tableau").path)

tool = initialize_simple_datasource_qa(
    domain=os.environ["TABLEAU_DOMAIN"],
    site=os.environ["TABLEAU_SITE"],
    jwt_client_id=os.environ["TABLEAU_JWT_CLIENT_ID"],
    jwt_secret_id=os.environ["TABLEAU_JWT_SECRET_ID"],
    jwt_secret=os.environ["TABLEAU_JWT_SECRET"],
    tableau_api_version=os.environ.get("TABLEAU_API_VERSION", "3.21"),
    tableau_user=os.environ["TABLEAU_USER"],
    datasource_luid=os.environ["DATASOURCE_LUID"],
    tooling_llm_model=os.environ.get("TOOLING_MODEL", "gpt-4o-mini"),
)

query_text = ("Return SUM(Sales), SUM(Profit), AVG(Discount) by State/Province, "
              "sorted by Profit desc.")

print("\n=== DIRECT TOOL INVOCATION ===")
try:
    print(tool.invoke(query_text))
except Exception:
    print("Tool error traceback:")
    traceback.print_exc()

print("\n=== AGENT INVOCATION ===")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
agent = create_react_agent(llm, [tool])
resp = agent.invoke({"messages":[("human", query_text)]})
print(resp["messages"][-1].content)
```

Run:

```bash
python quick_test.py
```

### B) Path sanity checks (macOS)

```bash
# Active python
which python
python -c "import sys; print(sys.executable)"

# Where is langchain_tableau imported from?
python - <<'PY'
import importlib.util, inspect, langchain_tableau as lct, os
print("module file:", importlib.util.find_spec("langchain_tableau").origin)
print("package dir:", os.path.dirname(inspect.getfile(lct)))
PY

# Open package directory in Finder or VS Code
open /opt/anaconda3/envs/tableau_langchain/lib/python3.12/site-packages/langchain_tableau
code  /opt/anaconda3/envs/tableau_langchain/lib/python3.12/site-packages/langchain_tableau
```

> If paths point to `/opt/anaconda3/lib/python3.12/...` (base env), your terminal/VS Code is using the wrong interpreter. Activate `tableau_langchain` and reselect it.

---

## 10) Troubleshooting Cheatsheet

| Symptom                         | Likely Cause                        | Fix                                                                                    |
| ------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------------- |
| `MissingSchema: Invalid URL`    | `TABLEAU_DOMAIN` missing `https://` | Set `https://10ax.online.tableau.com`                                                  |
| `401001 Signin Error`           | Wrong JWT/site/user                 | Verify Connected App IDs & secret, site name, `TABLEAU_USER`                           |
| `404 ... options->returnFormat` | Old/unsupported metadata params     | Use `POST /read-metadata` with simple payload                                          |
| `400` on `query-datasource`     | Wrong JSON shape/fields/functions   | Ensure `{"datasource": {...}, "query": {...}}`, valid `fieldCaption`, valid `function` |
| `KeyError('logicalTableId')`    | Unconditional indexing              | Use `.get("logicalTableId")`, keep LTID in prompt metadata                             |
| `403 Forbidden` (LangSmith)     | Tracing enabled sans creds          | Set `LANGSMITH_TRACING=false` or configure LangSmith                                   |
| `429 insufficient_quota`        | LLM quota exhausted                 | Use valid API key/plan; ensure correct env vars                                        |

---

## 11) What “Good” Looks Like

* **Metadata** returns **200** with fields; some include `logicalTableId`, some don’t.
* **Direct VDS** query returns **200** with expected aggregates (e.g., CA highest sales).
* **Agent** responds concisely with the answer (and small table snippet).
* No `KeyError('logicalTableId')`, no 401/403/404/400, no 429.

---

## 12) Appendix: Minimal VDS Helper (used by the tool)

```python
# experimental/utilities/vizql_data_service.py
import requests
from typing import Dict, Any

def query_vds(api_key: str, datasource_luid: str, url: str, query: Dict[str, Any]) -> Dict[str, Any]:
    full_url = f"{url}/api/v1/vizql-data-service/query-datasource"

    payload = {
        "datasource": {"datasourceLuid": datasource_luid},
        "query": query
    }

    headers = {
        "X-Tableau-Auth": api_key,
        "Content-Type": "application/json",
    }

    resp = requests.post(full_url, headers=headers, json=payload)
    if resp.status_code == 200:
        return resp.json()

    raise RuntimeError(
        f"Failed to query data source via Tableau VizQL Data Service. "
        f"Status code: {resp.status_code}. Response: {resp.text}"
    )

def query_vds_metadata(api_key: str, datasource_luid: str, url: str) -> Dict[str, Any]:
    full_url = f"{url}/api/v1/vizql-data-service/read-metadata"
    payload = {"datasource": {"datasourceLuid": datasource_luid}}
    headers = {"X-Tableau-Auth": api_key, "Content-Type": "application/json"}

    resp = requests.post(full_url, headers=headers, json=payload)
    if resp.status_code == 200:
        return resp.json()

    raise RuntimeError(
        f"Failed to obtain data source metadata from VizQL Data Service. "
        f"Status code: {resp.status_code}. Response: {resp.text}"
    )
```

---

**That’s it.** This guide covers everything you performed: environment setup, config, VDS metadata & query tests, running the agent, and the exact patches that eliminate `logicalTableId` crashes.