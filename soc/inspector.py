"""Learning views shared by the live conversation and historical runs."""
import json

import streamlit as st

from soc.execution import execution_events, graph_dot
from soc.evidence_summary import summarize_mcp
from soc.core import Investigation, estimate_context


def show_request(request, dropped=0, response=None):
    options = request.get("options", {})
    limit = options.get("num_ctx")
    reserve = options.get("num_predict", 0)
    rows = estimate_context(request)
    estimated = sum(row["estimated_tokens"] for row in rows)
    reported = (response or {}).get("prompt_eval_count")
    generated = (response or {}).get("eval_count")
    st.subheader("Context budget")
    a, b, c = st.columns(3)
    a.metric("Requested context limit", f"{limit:,}" if limit else "Not recorded")
    b.metric("Estimated input tokens", f"{estimated:,}")
    c.metric("Maximum output tokens", f"{reserve:,}")
    st.caption("Estimate: message characters ÷ 4, plus 8 tokens per message. Model templates and tokenization can differ substantially. The output schema is shown separately and is not included in this estimate.")
    if limit:
        st.progress(min((estimated + reserve) / limit, 1.0), text="Estimated input + maximum output / requested context")
        if estimated + reserve > limit:
            st.warning("Estimated input plus output allowance exceeds the requested window. Shorten the conversation or increase the context setting. This estimate cannot detect server truncation.")
    st.write(f"History policy: last 8 messages retained; {dropped} earlier messages omitted from this request.")
    st.dataframe(rows, width="stretch", hide_index=True)
    if response is not None:
        st.write(f"Ollama-reported input: {reported if reported is not None else 'unavailable'} tokens · generated output: {generated if generated is not None else 'unavailable'} tokens")
        if limit and reported is not None:
            st.progress(min(reported / limit, 1.0), text=f"Reported input / requested context: {reported / limit:.1%}")
            st.caption(f"Arithmetic space after reported input: {limit - reported:,} tokens. The requested limit is not a verified effective server limit; these counts do not prove the entire request was retained.")
    with st.expander("Exact API request", expanded=False):
        st.caption("This is the application payload. Ollama applies the model's chat template and any model configuration on the server.")
        for i, message in enumerate(request["messages"]):
            st.markdown(f"**Message {i + 1} · {message['role']}**")
            st.code(message["content"], language="text")
        st.markdown("**Output schema**")
        st.json(request["format"])
        st.markdown("**Complete payload (including settings)**")
        st.json(request)


def show_execution(run, location):
    events = execution_events(run)
    st.subheader("Investigation execution")
    st.caption("Recorded sequence · blue: recorded activity · green: passed/succeeded · amber: warning · red/orange: failed/rejected. Arrows show execution order, including repeated model turns. This is not live progress yet.")
    # Vertical layout avoids shrinking long execution sequences across the page.
    st.graphviz_chart(graph_dot(events, vertical=True), width="content")
    with st.expander("Inspect execution step details"):
        selected = st.selectbox("Inspect execution step", range(len(events)),
            format_func=lambda i: f"{i + 1}. {events[i]['title']} — {events[i]['status']}",
            key=f"execution-{location}-{run['id']}")
        st.json(events[selected]["detail"])
    if run.get("mode") == "mcp" or run.get("mcp_trace"):
        summary = summarize_mcp(run)
        if summary["warnings"]:
            st.warning("Evidence gathering needs review: " + " ".join(summary["warnings"]))
        requested = {e["detail"].get("tool") for e in events if e["kind"] == "tool"}
        not_called = [name for name in ("get_alert", "get_user", "query_login_events", "get_device_history") if name not in requested]
        if not_called:
            st.caption("No execution recorded for: " + ", ".join(not_called) + ". Inspect model turns to distinguish not requested from requested but not executed.")


def show_mcp_summary(run):
    if run.get("mode") != "mcp" and not run.get("mcp_trace"):
        return
    summary = summarize_mcp(run)
    st.subheader("MCP evidence summary")
    a, b, c = st.columns(3)
    a.metric("Events fetched", summary["event_count"])
    b.metric("User profile fetched", "Yes" if summary["user_fetched"] else "No")
    c.metric("Device-history records", summary["device_count"])
    if summary["successful_calls"]:
        st.write("Successful model-requested calls")
        st.dataframe(summary["successful_calls"], width="stretch", hide_index=True)
    else:
        st.info("No successful model-requested investigation calls recorded.")
    if summary["warnings"]:
        st.warning("Gathering is incomplete or needs review: " + " ".join(summary["warnings"]))
    else:
        st.success("User profile and event timeline were retrieved. This does not establish that the investigation is factually correct.")
    if summary["device_called"]:
        st.write("Additional MCP-only source: device history was retrieved. Retrieval does not prove it influenced the answer; inspect findings and citations.")
        st.dataframe(summary["evidence"].get("device_history", []), width="stretch")
    else:
        st.info("Device history was not successfully retrieved; no device-history evidence is attributed to this run.")
    if summary["problems"]:
        with st.expander("Rejected or failed investigation calls", expanded=True):
            st.json(summary["problems"])
    with st.expander("Collected MCP evidence (reference timeline vs additional device history)"):
        st.caption("events/user: retrieved from the same synthetic source shown as Scenario reference evidence. device_history: additional MCP-only source, absent from direct-mode input.")
        st.json(summary["evidence"])
    if summary["inspection"]:
        with st.expander("Process inspection only — server_info is not investigation evidence"):
            st.json(summary["inspection"])
    if "evidence_collected" not in run:
        st.caption("Older run: collected evidence is reconstructed where possible from recorded successful tool results. Missing fields are not assumed to have been fetched.")


def show_run(run, location="inspector"):
    show_execution(run, location)
    show_mcp_summary(run)
    if run.get("mode") == "mcp" and run.get("initial_request"):
        with st.expander("Initial alert-only request before MCP gathering"):
            st.json(run["initial_request"])
    show_request(run["request"], run.get("history_messages_dropped", 0), run.get("response"))
    if run.get("mcp_trace"):
        st.subheader("MCP execution trace")
        if run.get("mcp_evidence_warning"):
            st.warning(run["mcp_evidence_warning"])
        st.caption("Final response metrics below exclude intermediate model calls. Full intermediate usage is recorded in each tool-selection response; end-to-end latency includes all stages.")
        for index, step in enumerate(run["mcp_trace"], 1):
            with st.expander(f"{index}. {step['step']}"):
                st.json(step)
    st.subheader("Response inspection")
    raw, validated = st.columns(2)
    body = run.get("response") or {}
    with raw:
        st.markdown("**Raw model content**")
        st.code(body.get("message", {}).get("content", "No model content returned"), language="json")
        if body.get("message", {}).get("thinking"):
            with st.expander("Model-emitted thinking field"):
                st.code(body["message"]["thinking"], language="text")
        st.caption(f"Stop reason: {body.get('done_reason', 'not reported')}")
    with validated:
        st.markdown("**Validated application output**")
        if run["schema_valid"]:
            st.json(Investigation.model_validate_json(body["message"]["content"]).model_dump())
            st.success("Output schema passed")
        else:
            st.error(run.get("error") or "Schema validation failed")
        checks = run.get("checks")
        if checks:
            if checks["unknown_evidence_ids"]:
                st.warning(f"Unknown evidence IDs: {checks['unknown_evidence_ids']}")
            else:
                st.success(f"All {checks['citation_count']} citation references resolve to supplied evidence records")
        st.caption("Schema and citation checks do not evaluate whether the evidence supports the claim.")
    with st.expander("Full server response and run metadata"):
        st.json(run)
