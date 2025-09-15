# quick_test.py
import os, pkgutil, importlib
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_tableau.tools.simple_datasource_qa import initialize_simple_datasource_qa
import langchain_tableau

load_dotenv()
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")  # keep tracing off unless configured

# Show which langchain-tableau is actually loaded (path is helpful to confirm upgrades)
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
    tooling_llm_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
)

query_text = (
    "Return SUM(Sales), SUM(Profit), and AVG(Discount) by State/Province, "
    "sorted by Profit desc. Then answer if the top states by sales are the same as by profit."
)

print("\n=== DIRECT TOOL INVOCATION ===")
try:
    direct = tool.invoke(query_text)   # ensures the tool is actually used
    print(direct)
except Exception as e:
    print("Tool error:", repr(e))

print("\n=== AGENT INVOCATION ===")
llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)
agent = create_react_agent(llm, [tool])

resp = agent.invoke({"messages":[("human",
  "Use the Tableau tool to answer this exactly:\n" + query_text +
  "\n(Do not guess; call the tool.)"
)]})

print(resp["messages"][-1].content)



############################################################################
###### Data source verification

# import os, requests
# from dotenv import load_dotenv
# from langchain_tableau.utilities.auth import jwt_connected_app

# load_dotenv()

# auth = jwt_connected_app(
#     jwt_client_id=os.environ['TABLEAU_JWT_CLIENT_ID'],
#     jwt_secret_id=os.environ['TABLEAU_JWT_SECRET_ID'],
#     jwt_secret=os.environ['TABLEAU_JWT_SECRET'],
#     tableau_api=os.environ.get('TABLEAU_API_VERSION','3.21'),
#     tableau_user=os.environ['TABLEAU_USER'],
#     tableau_domain=os.environ['TABLEAU_DOMAIN'],
#     tableau_site=os.environ['TABLEAU_SITE'],
#     scopes=["tableau:content:read","tableau:viz_data_service:read"],
# )
# token = auth['credentials']['token']
# site_id = auth['credentials']['site']['id']
# domain = os.environ['TABLEAU_DOMAIN']
# ver = os.environ.get('TABLEAU_API_VERSION','3.21')
# ds = os.environ['DATASOURCE_LUID']

# r = requests.get(
#     f"{domain}/api/{ver}/sites/{site_id}/datasources/{ds}",
#     headers={"X-Tableau-Auth": token}
# )
# print("REST /datasources/{luid} =>", r.status_code)
# print(r.text[:800])


############################################################################
###### Check VDS read-metadata
# check_vds_metadata.py  (fixed)
# import os, requests, json
# from dotenv import load_dotenv
# from langchain_tableau.utilities.auth import jwt_connected_app

# load_dotenv()
# auth = jwt_connected_app(
#     jwt_client_id=os.environ['TABLEAU_JWT_CLIENT_ID'],
#     jwt_secret_id=os.environ['TABLEAU_JWT_SECRET_ID'],
#     jwt_secret=os.environ['TABLEAU_JWT_SECRET'],
#     tableau_api=os.environ.get('TABLEAU_API_VERSION','3.21'),
#     tableau_user=os.environ['TABLEAU_USER'],
#     tableau_domain=os.environ['TABLEAU_DOMAIN'],
#     tableau_site=os.environ['TABLEAU_SITE'],
#     scopes=["tableau:content:read","tableau:viz_data_service:read"],
# )

# token  = auth['credentials']['token']
# domain = os.environ['TABLEAU_DOMAIN']
# luid   = os.environ['DATASOURCE_LUID']

# resp = requests.post(
#     f"{domain}/api/v1/vizql-data-service/read-metadata",
#     headers={"X-Tableau-Auth": token, "Content-Type": "application/json"},
#     json={"datasource": {"datasourceLuid": luid}, "options": {"debug": True}},  # debug is allowed
# )
# print("VDS read-metadata =>", resp.status_code)
# print(resp.text[:2000])

# if resp.ok:
#     fields = resp.json().get("data", [])
#     print("Total fields:", len(fields))
#     for f in fields[:25]:
#         cap = f.get("fieldCaption") or f.get("caption") or f.get("name")
#         print("-", cap, "| logicalTableId present?", "logicalTableId" in f)


