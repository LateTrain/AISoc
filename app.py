import json

import httpx
import pandas as pd
import streamlit as st

from soc.core import Investigation, build_request, investigate, load_runs
from soc.inspector import show_request, show_run, show_mcp_summary, show_execution, show_compact_summary
from soc.data import SCENARIOS
from soc.mcp_client import demo
from soc.evidence_summary import summarize_mcp

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
    with st.expander("Inference settings", expanded=False):
        temperature = st.slider("Temperature", 0.0, 2.0, 0.0, 0.05, help="Controls sampling randomness. Zero selects the most likely tokens; higher values allow more variation.")
        top_p = st.slider("Top-p", 0.05, 1.0, 0.9, 0.05, help="Restricts sampling to candidates covering this cumulative probability mass.")
        top_k = st.number_input("Top-k", min_value=0, max_value=1000, value=40, help="Limits candidate tokens to the top K. Zero disables this filter.")
        repeat_penalty = st.slider("Repeat penalty", 0.1, 2.0, 1.1, 0.05, help="1.0 is neutral; larger values discourage repetition.")
        fixed_seed = st.checkbox("Use a fixed seed", help="Helps compare runs, but does not guarantee identical results across hardware or software versions.")
        seed = st.number_input("Seed", min_value=1, max_value=2147483647, value=42, disabled=not fixed_seed)
        st.caption("Sent as API options, separately from the system prompt. At temperature 0, sampling filters and seed may have little or no visible effect.")
    sampling = dict(temperature=temperature, top_p=top_p, top_k=int(top_k), repeat_penalty=repeat_penalty, seed=int(seed) if fixed_seed else None)
    mcp_mode = st.checkbox("Gather evidence through MCP", value=True, help="Starts with alert metadata; the model requests evidence from a separate Python process.")
    scenario = st.selectbox("Scenario", list(SCENARIOS), key="scenario")
    st.caption("Change models to compare saved runs. No model downloads are triggered.")
    def clear_conversation():
        st.session_state.pop("chat", None)
        st.session_state.pop("last_run", None)
    st.button("Clear conversation", on_click=clear_conversation)

context = (scenario, model, host, mcp_mode)
if st.session_state.get("context") != context:
    st.session_state.chat = []
    st.session_state.pop("last_run", None)
    st.session_state.context = context
chat = st.session_state.setdefault("chat", [])
evidence = SCENARIOS[scenario]
def submit_question(question):
    question = question or "Investigate this alert. What happened, what is uncertain, and what should we check next?"
    with st.spinner("Waiting for Ollama…"):
        run = investigate(question, evidence, model, host, chat, scenario, num_ctx=int(num_ctx), num_predict=int(num_predict), mcp_mode=mcp_mode, **sampling)
    st.session_state.last_run = run["id"]
    if run["schema_valid"]:
        chat.extend([{"role": "user", "content": question},
                     {"role": "assistant", "run_id": run["id"], "content": Investigation.model_validate_json(run["response"]["message"]["content"]).model_dump_json()}])
        st.session_state.last_run = run["id"]
        st.rerun()
    else:
        st.error(f"Investigation failed; saved in monitoring. {run['error']}")
        show_compact_summary(run)

simple_tab, investigation_tab, learning_tab, mcp_tab, monitoring_tab = st.tabs(["Simple Q&A", "Investigation", "Learning inspector", "MCP lab", "Model monitoring"])
with simple_tab:
    st.subheader("Selected alert")
    st.write(evidence["alert"])
    st.caption(f"Scenario: {scenario} · Alert: alert-{list(SCENARIOS).index(scenario) + 1} · User: {evidence['user']['id']}")
    st.caption("The analyst starts with this alert and requests supporting evidence through MCP." if mcp_mode else "The analyst receives this alert and the scenario's supporting evidence directly.")
    st.divider()
    st.caption("Same investigation and conversation, formatted for reading. Technical details are in the other tabs.")
    for message in chat:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.write(message["content"])
            else:
                answer = Investigation.model_validate_json(message["content"])
                st.write(answer.summary)
                if answer.findings:
                    st.markdown("**Findings**")
                    for finding in answer.findings:
                        st.write(f"• {finding.claim}")
                        st.caption("Evidence: " + ", ".join(finding.evidence_ids))
                if answer.uncertainty:
                    st.markdown("**Uncertainty**")
                    for item in answer.uncertainty:
                        st.write(f"• {item}")
                if answer.next_steps:
                    st.markdown("**Next steps**")
                    for number, item in enumerate(answer.next_steps, 1):
                        st.write(f"{number}. {item}")
                saved = next((r for r in load_runs() if r["id"] == message.get("run_id")), None)
                if saved:
                    if saved.get("mode") == "mcp":
                        warnings = summarize_mcp(saved)["warnings"]
                        if warnings:
                            st.warning("Evidence gathering needs review: " + " ".join(warnings))
                    if (saved.get("checks") or {}).get("unknown_evidence_ids"):
                        st.warning("Some evidence references are invalid. Review the investigation details.")
    if not chat:
        st.info("Ask a question below, or use Investigate this alert in the Investigation tab.")
    with st.form("simple-question", clear_on_submit=True):
        simple_question = st.text_input("Your question", placeholder="Investigate this alert and check device history")
        submitted = st.form_submit_button("Ask")
    if submitted:
        if simple_question.strip():
            submit_question(simple_question.strip())
        else:
            st.info("Enter a question first.")

with investigation_tab:
    left, right = st.columns([3, 2])
    with right:
        if mcp_mode:
            st.subheader("Incoming alert")
            st.json({"alert_id": f"alert-{list(SCENARIOS).index(scenario) + 1}",
                     "alert": evidence["alert"], "user_id": evidence["user"]["id"]})
            st.caption("The model starts with only this metadata. It must request supporting evidence through MCP.")
            current_run = next((r for r in load_runs() if r["id"] == st.session_state.get("last_run")), None)
            st.subheader("Retrieved investigation evidence")
            if current_run:
                collected = summarize_mcp(current_run)["evidence"]
                st.caption("Latest investigation only. These records came from successful MCP calls; no fixture fallback is used.")
                if collected.get("user"):
                    st.markdown("**User profile · get_user**")
                    st.json(collected["user"])
                if collected.get("events"):
                    st.markdown("**Event timeline · query_login_events**")
                    st.dataframe(collected["events"], width="stretch")
                if collected.get("device_history"):
                    st.markdown("**Device history · get_device_history**")
                    st.dataframe(collected["device_history"], width="stretch")
                if not any(collected.get(key) for key in ("user", "events", "device_history")):
                    st.info("No supporting evidence was retrieved in this run.")
            else:
                st.info("No evidence retrieved yet. Submit an investigation to see what the model fetches.")
            with st.expander("Scenario reference evidence (profile and event timeline)"):
                st.caption("Learning reference only. These profile and timeline fixtures are not automatically supplied to the model in MCP mode. Device history is a separate MCP-only source.")
                st.write(evidence["alert"])
                st.json(evidence["user"])
                st.dataframe(evidence["events"], width="stretch")
        else:
            st.subheader("Supplied investigation evidence")
            st.write(evidence["alert"])
            st.json(evidence["user"])
            st.dataframe(evidence["events"], width="stretch")
            st.caption("Direct mode supplies this evidence with the request. Device history is not included.")
    with left:
        st.subheader("Analyst chat")
        for message in chat:
            with st.chat_message(message["role"]):
                if message["role"] == "assistant":
                    st.json(json.loads(message["content"]))
                    saved = next((r for r in load_runs() if r["id"] == message.get("run_id")), None)
                    if saved:
                        show_compact_summary(saved)
                else:
                    st.write(message["content"])
        initial = st.button("Investigate this alert", disabled=bool(chat))
        question = st.chat_input("Ask about the evidence or request a follow-up")
        if initial or question:
            submit_question(question)

with learning_tab:
    st.subheader("Preview your next request")
    preview = st.text_area("Question to preview", "Investigate this alert. What happened, what is uncertain, and what should we check next?")
    st.caption("Preview only: submit your question through Analyst chat. This panel makes no model calls.")
    if mcp_mode:
        st.write("Initial alert metadata preview")
        st.json({"alert_id": f"alert-{list(SCENARIOS).index(scenario) + 1}", "alert": evidence["alert"], "user_id": evidence["user"]["id"]})
        st.write("Question: " + preview)
        st.caption("No conversation history is retained in MCP mode. Tool definitions are discovered when the investigation starts; inspect the recorded tool-selection requests afterward.")
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
            st.session_state.mcp_demo_scenario = scenario
            st.session_state.mcp_demo = demo(f"alert-{list(SCENARIOS).index(scenario) + 1}")
    if st.session_state.get("mcp_demo"):
        st.caption("Displayed demo scenario: " + st.session_state.get("mcp_demo_scenario", "Not recorded"))
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
        for row, recorded in zip(rows, runs):
            if recorded.get("mode") == "mcp":
                summary = summarize_mcp(recorded)
                row.update(events_fetched=summary["event_count"], device_records=summary["device_count"], user_profile=summary["user_fetched"], tools_used=", ".join(c["tool"] for c in summary["successful_calls"]), gathering_warnings=" ".join(summary["warnings"]))
            row["unknown_citations"] = ", ".join((recorded.get("checks") or {}).get("unknown_evidence_ids", []))
        frame = pd.DataFrame(rows)
        a, b, c = st.columns(3)
        a.metric("Runs", len(runs))
        b.metric("API / schema errors", sum(r["status"] == "error" for r in runs))
        c.metric("Citation warnings", sum(r["status"] == "citation_warning" for r in runs))
        st.dataframe(frame, width="stretch")
        with st.expander("Compare two saved experiments"):
            labels = lambda i: f"{runs[i]['timestamp']} · {runs[i]['model']} · {runs[i]['scenario']} · {runs[i].get('mode', 'direct')}"
            first = st.selectbox("First run", range(len(runs)), format_func=labels)
            second = st.selectbox("Second run", range(len(runs)), index=min(1, len(runs)-1), format_func=labels)
            comparison = []
            for index in (first, second):
                item = runs[index]
                summary = summarize_mcp(item)
                question = item.get("submission", {}).get("question") or item.get("request", {}).get("messages", [{}])[-1].get("content")
                comparison.append({"Run": item["id"], "Model": item["model"], "Scenario": item["scenario"], "Mode": item.get("mode", "direct"), "Question": question, "Settings": item["request"].get("options", {}), "Prompt version": item.get("prompt_version"), "Latency seconds": item.get("latency_s"), "Status": item.get("status"), "Tools": [c["tool"] for c in summary["successful_calls"]], "Citation warnings": (item.get("checks") or {}).get("unknown_evidence_ids", [])})
            st.json(comparison)
            st.caption("Compare matching questions, history, scenarios, modes, prompt versions, and settings. Latency includes model loading and failures; final token counts exclude intermediate calls.")
        selected = st.selectbox("Inspect a run", range(len(runs)), format_func=lambda i: f"{runs[i]['timestamp']} · {runs[i]['model']} · {runs[i]['scenario']}")
        run = runs[selected]
        if run["checks"] and run["checks"]["unknown_evidence_ids"]:
            st.warning(f"Unknown evidence IDs: {run['checks']['unknown_evidence_ids']}")
        show_run(run, "monitoring")
        st.download_button("Export runs (JSON)", json.dumps(runs, indent=2), "soc-runs.json", "application/json")
