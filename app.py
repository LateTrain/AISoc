import json

import httpx
import pandas as pd
import streamlit as st

from soc.core import Investigation, build_request, investigate, load_runs
from soc.inspector import show_request, show_run
from soc.data import SCENARIOS
from soc.mcp_client import demo

st.set_page_config(page_title="AI SOC Lab", page_icon="🔎", layout="wide")
st.title("AI SOC Lab")
st.caption("Synthetic investigations · local Ollama · observable model experiments")
with st.sidebar:
    st.header("Experiment settings")
    host = st.text_input("Ollama URL", "http://localhost:11434")
    model = st.text_input("Model", "llama3.2:latest")
    if st.button("Check Ollama / list models"):
        try:
            r = httpx.get(host.rstrip("/") + "/api/tags", timeout=5, trust_env=False)
            r.raise_for_status()
            st.write([m["name"] for m in r.json()["models"]])
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            st.error(f"Could not connect: {exc}")
    num_ctx = st.number_input("Requested context tokens", min_value=2048, max_value=131072, value=4096, step=1024)
    num_predict = st.number_input("Maximum output tokens", min_value=128, max_value=int(num_ctx) - 1, value=1200, step=128)
    with st.expander("Inference settings", expanded=True):
        temperature = st.slider("Temperature", 0.0, 2.0, 0.0, 0.05, help="Controls sampling randomness. Zero selects the most likely tokens; higher values allow more variation.")
        top_p = st.slider("Top-p", 0.05, 1.0, 0.9, 0.05, help="Restricts sampling to candidates covering this cumulative probability mass.")
        top_k = st.number_input("Top-k", min_value=0, max_value=1000, value=40, help="Limits candidate tokens to the top K. Zero disables this filter.")
        repeat_penalty = st.slider("Repeat penalty", 0.1, 2.0, 1.1, 0.05, help="1.0 is neutral; larger values discourage repetition.")
        fixed_seed = st.checkbox("Use a fixed seed", help="Helps compare runs, but does not guarantee identical results across hardware or software versions.")
        seed = st.number_input("Seed", min_value=1, max_value=2147483647, value=42, disabled=not fixed_seed)
        st.caption("Sent as API options, separately from the system prompt. At temperature 0, sampling filters and seed may have little or no visible effect.")
    sampling = dict(temperature=temperature, top_p=top_p, top_k=int(top_k), repeat_penalty=repeat_penalty, seed=int(seed) if fixed_seed else None)
    mcp_mode = st.checkbox("Gather evidence through MCP", help="Starts with alert metadata; the model requests evidence from a separate Python process.")
    scenario = st.selectbox("Scenario", list(SCENARIOS), key="scenario")
    st.caption("Change models to compare saved runs. No model downloads are triggered.")
    st.button("Clear conversation", on_click=lambda: st.session_state.pop("chat", None))

context = (scenario, model, host, mcp_mode)
if st.session_state.get("context") != context:
    st.session_state.chat = []
    st.session_state.pop("last_run", None)
    st.session_state.context = context
chat = st.session_state.setdefault("chat", [])
evidence = SCENARIOS[scenario]
investigation_tab, learning_tab, mcp_tab, monitoring_tab = st.tabs(["Investigation", "Learning inspector", "MCP lab", "Model monitoring"])
with investigation_tab:
    left, right = st.columns([3, 2])
    with right:
        st.subheader("Supplied evidence")
        st.write(evidence["alert"])
        st.json(evidence["user"])
        st.dataframe(evidence["events"], width="stretch")
        st.caption("Fixture reference: in MCP mode the model initially receives only alert metadata and must fetch supporting evidence through tools." if mcp_mode else "All evidence is supplied directly. Enable MCP mode to fetch it through tools.")
    with left:
        st.subheader("Analyst chat")
        for message in chat:
            with st.chat_message(message["role"]):
                if message["role"] == "assistant":
                    st.json(json.loads(message["content"]))
                else:
                    st.write(message["content"])
        initial = st.button("Investigate this alert", disabled=bool(chat))
        question = st.chat_input("Ask about the evidence or request a follow-up")
        if initial or question:
            question = question or "Investigate this alert. What happened, what is uncertain, and what should we check next?"
            with st.spinner("Waiting for Ollama…"):
                run = investigate(question, evidence, model, host, chat, scenario, num_ctx=int(num_ctx), num_predict=int(num_predict), mcp_mode=mcp_mode, **sampling)
            st.session_state.last_run = run["id"]
            if run["schema_valid"]:
                chat.extend([{"role": "user", "content": question},
                             {"role": "assistant", "content": Investigation.model_validate_json(run["response"]["message"]["content"]).model_dump_json()}])
                st.session_state.last_run = run["id"]
                st.rerun()
            else:
                st.error(f"Investigation failed; saved in monitoring. {run['error']}")

with learning_tab:
    st.subheader("Preview your next request")
    preview = st.text_area("Question to preview", "Investigate this alert. What happened, what is uncertain, and what should we check next?")
    st.caption("Preview only: submit your question through Analyst chat. This panel makes no model calls.")
    if mcp_mode:
        st.info("MCP mode begins with alert metadata and discovered tools. Inspect exact tool-selection requests and the final evidence request in the saved run trace.")
    else:
        show_request(build_request(preview, evidence, model, chat, int(num_ctx), int(num_predict), **sampling), max(0, len(chat) - 8))
    latest = next((r for r in load_runs() if r["id"] == st.session_state.get("last_run")), None)
    if latest:
        st.divider()
        st.subheader("Last submitted request and response")
        show_run(latest)
    else:
        st.info("Submit a chat question to inspect its actual request and response here. Historical runs are available in Model monitoring.")

with mcp_tab:
    st.subheader("MCP over stdio")
    st.write("SOC app → stdin pipe → separate Python tool-provider process → stdout pipe → SOC app")
    st.caption("The app launches and initializes the server, discovers tools, and calls them. Each connection stops its child process on completion. This is actual MCP, not simulated tool calls.")
    if st.button("Discover tools and fetch sample evidence (no model)"):
        with st.spinner("Starting MCP server and calling tools…"):
            st.session_state.mcp_demo = demo(f"alert-{list(SCENARIOS).index(scenario) + 1}")
    for step in st.session_state.get("mcp_demo", []):
        with st.expander(step["step"], expanded=True):
            st.json(step)
    st.info("Enable Gather evidence through MCP in the sidebar, then investigate an alert to see model-selected calls. Model tool support and selection quality vary.")

with monitoring_tab:
    st.subheader("Saved runs")
    st.caption("Operational metrics and format/citation checks. Citation existence does not establish factual correctness. Human review is still needed; drift and semantic quality scoring are future work.")
    runs = load_runs()
    if not runs:
        st.info("Run an investigation to collect your first measurements.")
    else:
        rows = [{"model": r["model"], "scenario": r["scenario"], "timestamp": r["timestamp"],
                 "mode": r.get("mode", "direct"), "status": r["status"], "latency_s": r["latency_s"],
                 "schema_valid": r["schema_valid"],
                 **{k: r["request"]["options"].get(k) for k in ("temperature", "top_p", "top_k", "repeat_penalty", "seed")},
                 "input_tokens": r["metrics"].get("prompt_eval_count"),
                 "output_tokens": r["metrics"].get("eval_count"),
                 "tokens_per_second": r["metrics"].get("tokens_per_second")} for r in runs]
        frame = pd.DataFrame(rows)
        a, b, c = st.columns(3)
        a.metric("Runs", len(runs))
        b.metric("API / schema errors", sum(r["status"] == "error" for r in runs))
        c.metric("Citation warnings", sum(r["status"] == "citation_warning" for r in runs))
        st.dataframe(frame, width="stretch")
        st.write("Latency by model (includes failures and model loading)")
        st.dataframe(frame.groupby("model").agg(runs=("model", "size"), median_latency_s=("latency_s", "median")), width="stretch")
        selected = st.selectbox("Inspect a run", range(len(runs)), format_func=lambda i: f"{runs[i]['timestamp']} · {runs[i]['model']} · {runs[i]['scenario']}")
        run = runs[selected]
        if run["checks"] and run["checks"]["unknown_evidence_ids"]:
            st.warning(f"Unknown evidence IDs: {run['checks']['unknown_evidence_ids']}")
        show_run(run)
        st.download_button("Export runs (JSON)", json.dumps(runs, indent=2), "soc-runs.json", "application/json")
