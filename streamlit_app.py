# ──────────────────────────────────────────────────────────────────────────────
# Load .env from this file’s directory (works even when Streamlit changes cwd)
# ──────────────────────────────────────────────────────────────────────────────
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# Disable LangSmith tracing to avoid 403/telemetry surprises
import os
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGSMITH_ENDPOINT", "")
os.environ.setdefault("LANGSMITH_API_KEY", "")

import uuid
import json
import traceback
from typing import Dict, List, Tuple

import streamlit as st

# LLM / Agent bits
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

# Tableau tool and direct VDS helpers
from langchain_tableau.tools.simple_datasource_qa import initialize_simple_datasource_qa
from langchain_tableau.utilities.auth import jwt_connected_app
from experimental.utilities.vizql_data_service import query_vds, query_vds_metadata

# Optional: show where the package is actually loaded from
import importlib.util, langchain_tableau as lct

# ──────────────────────────────────────────────────────────────────────────────
# App config
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Tableau Agent", page_icon="📊", layout="wide")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def env_or_error(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v

def get_messages_payload(chat_log: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    payload: List[Tuple[str, str]] = []
    for role, content in chat_log:
        payload.append(("human", content) if role == "user" else ("ai", content))
    return payload


# ──────────────────────────────────────────────────────────────────────────────
# Build tool & agent only once
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def build_agent():
    domain = env_or_error("TABLEAU_DOMAIN")
    site = env_or_error("TABLEAU_SITE")
    jwt_client_id = env_or_error("TABLEAU_JWT_CLIENT_ID")
    jwt_secret_id = env_or_error("TABLEAU_JWT_SECRET_ID")
    jwt_secret = env_or_error("TABLEAU_JWT_SECRET")
    tableau_api_version = os.getenv("TABLEAU_API_VERSION", "3.21")
    tableau_user = env_or_error("TABLEAU_USER")
    datasource_luid = env_or_error("DATASOURCE_LUID")

    chat_model = os.getenv("CHAT_MODEL", "gpt-4o-mini")
    tooling_model = os.getenv("TOOLING_MODEL", "gpt-4o-mini")

    tool = initialize_simple_datasource_qa(
        domain=domain,
        site=site,
        jwt_client_id=jwt_client_id,
        jwt_secret_id=jwt_secret_id,
        jwt_secret=jwt_secret,
        tableau_api_version=tableau_api_version,
        tableau_user=tableau_user,
        datasource_luid=datasource_luid,
        tooling_llm_model=tooling_model,
    )

    llm = ChatOpenAI(model=chat_model, temperature=0)
    base_agent = create_react_agent(llm, [tool])
    return base_agent

agent = build_agent()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar: Settings & Environment checks
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Settings")

    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())
    st.text_input("Session ID", value=st.session_state["session_id"], disabled=True)

    if st.button("🔄 New chat (reset memory)", use_container_width=True):
        st.session_state["chat_log"] = []
        st.session_state["session_id"] = str(uuid.uuid4())
        st.rerun()

    st.divider()
    dev_stream = st.toggle("Developer streaming (show agent/tool events)", value=False, help="Streams ReAct events to help debug tool calls.")

    st.caption("**Environment checks**")
    env_ok = True
    for var in [
        "TABLEAU_DOMAIN", "TABLEAU_SITE", "TABLEAU_JWT_CLIENT_ID", "TABLEAU_JWT_SECRET_ID",
        "TABLEAU_JWT_SECRET", "TABLEAU_API_VERSION", "TABLEAU_USER", "DATASOURCE_LUID",
        "OPENAI_API_KEY",
    ]:
        ok = bool(os.getenv(var))
        env_ok = env_ok and ok
        st.write(f"{'✅' if ok else '❌'} {var}")
    if not env_ok:
        st.warning("Missing one or more environment variables. Update your .env and restart.", icon="⚠️")

    st.divider()
    st.caption("**Package paths**")
    spec = importlib.util.find_spec("langchain_tableau")
    st.write("langchain-tableau path:", spec.origin if spec else "not found")
    st.write("langchain-tableau version:", getattr(lct, "__version__", "unknown"))


# ──────────────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────────────
st.title("📊 Tableau Agent (Streamlit)")
st.caption("Ask analytics questions—answers come from your Tableau datasource via VizQL Data Service.")


# ──────────────────────────────────────────────────────────────────────────────
# Connectivity Diagnostics (auth + VDS sanity check)
# ──────────────────────────────────────────────────────────────────────────────
with st.expander("🔎 Connectivity Diagnostics"):
    if st.button("Run Tableau auth + VDS checks"):
        try:
            domain = env_or_error("TABLEAU_DOMAIN")
            site = env_or_error("TABLEAU_SITE")
            datasource_luid = env_or_error("DATASOURCE_LUID")

            tableau_auth = jwt_connected_app(
                jwt_client_id=env_or_error("TABLEAU_JWT_CLIENT_ID"),
                jwt_secret_id=env_or_error("TABLEAU_JWT_SECRET_ID"),
                jwt_secret=env_or_error("TABLEAU_JWT_SECRET"),
                tableau_api=os.getenv("TABLEAU_API_VERSION", "3.21"),
                tableau_user=env_or_error("TABLEAU_USER"),
                tableau_domain=domain,
                tableau_site=site,
                scopes=["tableau:content:read", "tableau:viz_data_service:read"],
            )
            token = tableau_auth["credentials"]["token"]
            st.success("✅ Authenticated to Tableau (X-Tableau-Auth acquired).")

            st.write("**VDS read-metadata (sample fields)**")
            md = query_vds_metadata(api_key=token, datasource_luid=datasource_luid, url=domain)
            st.json(md if isinstance(md, dict) else json.loads(md))

            body = {
                "fields": [
                    {"fieldCaption": "Region", "sortPriority": 1},
                    {"fieldCaption": "Discount", "function": "AVG"},
                    {"fieldCaption": "Sales", "function": "SUM"},
                    {"fieldCaption": "Profit", "function": "SUM", "sortDirection": "DESC", "sortPriority": 2},
                ]
            }
            st.write("**DEBUG VDS BODY**")
            st.code(json.dumps(
                {
                    "datasource": {"datasourceLuid": datasource_luid},
                    "query": body,
                    "options": {"returnFormat": "OBJECTS", "debug": True, "disaggregate": False},
                },
                indent=2,
            ), language="json")

            data = query_vds(api_key=token, datasource_luid=datasource_luid, url=domain, query=body)
            st.write("**VDS query-datasource (data)**")
            st.json(data if isinstance(data, dict) else json.loads(data))

        except Exception as e:
            st.error(f"❌ Diagnostics failed: {e}")
            st.code(traceback.format_exc())


# ──────────────────────────────────────────────────────────────────────────────
# Chat area with session memory
# ──────────────────────────────────────────────────────────────────────────────
if "chat_log" not in st.session_state:
    st.session_state["chat_log"] = []   # list[("user"|"assistant", text)]

# Render history
for role, content in st.session_state["chat_log"]:
    with st.chat_message("assistant" if role == "assistant" else "user"):
        st.markdown(content)

raw_prompt = st.chat_input("Ask a question about your data… (e.g., Top states by sales vs profit)")

if raw_prompt is not None:
    prompt = raw_prompt.strip()
    if prompt:
        st.session_state["chat_log"].append(("user", prompt))

        # Build full conversation payload (prevents empty 'messages' errors)
        messages_payload = get_messages_payload(st.session_state["chat_log"])

        with st.chat_message("assistant"):
            placeholder = st.empty()
            try:
                # Developer streaming: inspect tool events/messages
                if dev_stream:
                    with st.expander("🔧 Agent/Tool event stream"):
                        final_resp = None
                        for event in agent.stream({"messages": messages_payload}):
                            st.write(event)  # raw chunks; useful to see tool calls & errors
                            final_resp = event
                        # The last chunk contains the final state; ask agent for final response too:
                        resp = agent.invoke({"messages": messages_payload})
                else:
                    resp = agent.invoke(
                        {"messages": messages_payload},
                        config={"configurable": {"session_id": st.session_state["session_id"]}},
                    )

                answer = resp["messages"][-1].content if isinstance(resp, dict) else str(resp)

                # If the agent returned the unhelpful fallback, run a known-good VDS query as a safety net
                generic_fail = "persistent issue" in answer.lower() or "unable to access" in answer.lower()
                if generic_fail:
                    domain = env_or_error("TABLEAU_DOMAIN")
                    site = env_or_error("TABLEAU_SITE")
                    datasource_luid = env_or_error("DATASOURCE_LUID")
                    tableau_auth = jwt_connected_app(
                        jwt_client_id=env_or_error("TABLEAU_JWT_CLIENT_ID"),
                        jwt_secret_id=env_or_error("TABLEAU_JWT_SECRET_ID"),
                        jwt_secret=env_or_error("TABLEAU_JWT_SECRET"),
                        tableau_api=os.getenv("TABLEAU_API_VERSION", "3.21"),
                        tableau_user=env_or_error("TABLEAU_USER"),
                        tableau_domain=domain,
                        tableau_site=site,
                        scopes=["tableau:content:read", "tableau:viz_data_service:read"],
                    )
                    token = tableau_auth["credentials"]["token"]

                    # Simple heuristic: if the prompt mentions region/sales/profit/discount,
                    # fallback to your proven query body
                    lower = prompt.lower()
                    if any(k in lower for k in ["region", "profit", "sales", "discount"]):
                        body = {
                            "fields": [
                                {"fieldCaption": "Region", "sortPriority": 1},
                                {"fieldCaption": "Discount", "function": "AVG"},
                                {"fieldCaption": "Sales", "function": "SUM"},
                                {"fieldCaption": "Profit", "function": "SUM", "sortDirection": "DESC", "sortPriority": 2},
                            ]
                        }
                        data = query_vds(api_key=token, datasource_luid=datasource_luid, url=domain, query=body)
                        rows = data.get("data", [])
                        if rows:
                            # Render a concise answer + table
                            md = ["**Fallback (direct VDS) — Region summary:**"]
                            for r in rows:
                                md.append(
                                    f"- **{r['Region']}** — AVG(Discount): {r['AVG(Discount)']:.2%} | "
                                    f"SUM(Sales): ${r['SUM(Sales)']:,.2f} | SUM(Profit): ${r['SUM(Profit)']:,.2f}"
                                )
                            answer = "\n".join(md)
                        else:
                            answer = "The fallback VDS query returned no rows."

                placeholder.markdown(answer)
                st.session_state["chat_log"].append(("assistant", answer))

            except Exception:
                err_text = traceback.format_exc()
                placeholder.error("Tool/Agent error — see details below.")
                st.code(err_text)
                st.session_state["chat_log"].append(("assistant", f"Error:\n```\n{err_text}\n```"))

                
