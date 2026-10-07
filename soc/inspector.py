"""Learning views shared by the live conversation and historical runs."""
import json

import streamlit as st

from soc.execution import execution_events, graph_dot
from soc.evidence_summary import summarize_mcp
from soc.core import Investigation, estimate_context


def show_request(request, dropped=0, response=None, mcp=False):
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
    st.write("History policy: MCP investigations do not retain conversation history." if mcp else f"History policy: last 8 messages retained; {dropped} earlier messages omitted from this request.")
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


def final_evidence(run):
    """Read the evidence actually present in the final request, including old runs."""
    try:
        message = run["request"]["messages"][1]["content"]
        if not message.startswith("Evidence:\n"):
            return {}
        return json.loads(message.split("\n", 1)[1])
    except (KeyError, IndexError, ValueError, TypeError):
        return {}


def show_findings(run):
    evidence = final_evidence(run)
    records = {record["id"]: (record, source) for key, source in
               (("events", "query_login_events"), ("device_history", "get_device_history"))
               for record in evidence.get(key, []) if "id" in record}
    try:
        answer = json.loads((run.get("response") or {})["message"]["content"])
    except (KeyError, ValueError, TypeError):
        st.info("No readable final findings recorded.")
        return
    st.caption("These records were included in final generation. A matching citation does not prove that the record supports the claim.")
    for index, finding in enumerate(answer.get("findings", []), 1):
        with st.expander(f"Finding {index}: {finding.get('claim', '')}"):
            for citation in finding.get("evidence_ids", []):
                if citation not in records:
                    st.warning(f"{citation}: not found in final-generation evidence.")
                    continue
                record, tool = records[citation]
                st.write(f"{citation} · " + (f"Retrieved through {tool}" if run.get("mode") == "mcp" else "Supplied directly"))
                st.json(record)


def show_tool_outcomes(run):
    trace = run.get("mcp_trace", [])
    names = {tool["name"] for step in trace if step.get("step") == "MCP tools/list"
             for tool in step.get("tools", []) if tool["name"] != "server_info"}
    requests = []
    for step in trace:
        if step.get("step") == "Model tool selection":
            requests.extend(call.get("function", {}) for call in step.get("response", {}).get("message", {}).get("tool_calls", []) or [])
    names.update(call.get("name") for call in requests if call.get("name"))
    rows = []
    for name in sorted(names):
        attempts = [step for step in trace if step.get("tool") == name and step.get("step") in {"MCP tools/call", "Rejected tool", "Failed tool call"}]
        outcomes = []
        for step in attempts:
            if step["step"] == "Rejected tool":
                outcomes.append("Rejected")
            elif step["step"] == "Failed tool call" or step.get("result", {}).get("isError"):
                outcomes.append("Failed")
            elif step.get("result", {}).get("isError") is False:
                outcomes.append("Succeeded")
            else:
                outcomes.append("Outcome unknown")
        if not outcomes:
            outcomes = ["Requested but not executed" if any(call.get("name") == name for call in requests) else "Not requested"]
        rows.append({"Tool": name, "Role": "Required evidence" if name in {"get_user", "query_login_events"} else "Optional", "Recorded outcomes": ", ".join(outcomes)})
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info("No tool discovery or selection recorded.")
    st.caption("An unused optional tool is not automatically a failure. Repeated attempts may have different outcomes; inspect the execution steps.")


def show_compact_summary(run):
    if run.get("mode") != "mcp":
        return
    summary = summarize_mcp(run)
    st.write(f"MCP: {len(summary['successful_calls'])} successful calls · {summary['event_count']} events · {summary['device_count']} device records · user profile: {'yes' if summary['user_fetched'] else 'no'}")
    for warning in summary["warnings"]:
        st.warning(warning)
    st.caption("Open Learning inspector to follow requests, results, and citations.")


def show_run(run, location="inspector"):
    mcp = run.get("mode") == "mcp"
    st.caption("Follow one investigation from its initial input to its final answer. Details below are recorded results, not live progress.")
    with st.expander("Execution overview"):
        show_execution(run, location)
    with st.expander("1. Initial input", expanded=True):
        initial = run.get("initial_request")
        if initial:
            st.json(initial)
        else:
            st.info("Initial payload was not stored in this older run.")
        st.caption("Prepared application payload; this is not a record of transmission. In MCP mode, tool definitions are added after discovery. Older runs may show an instruction that was replaced before transmission.")
        selections = [step for step in run.get("mcp_trace", []) if step.get("step") == "Model tool selection"]
        if mcp and selections:
            st.markdown("**Actual system message sent for evidence gathering**")
            for index, step in enumerate(selections, 1):
                messages = step.get("request", {}).get("messages", [])
                system = next((message.get("content", "") for message in messages if message.get("role") == "system"), None)
                if system is not None:
                    st.code(system, language="text")
                    st.caption(f"Recorded gathering turn {step.get('turn', index)}. Complete requests appear in stage 3.")
                    break
            else:
                st.info("The actual gathering system message was not recorded.")
        st.write("MCP mode investigates each question without conversation history." if mcp else "Direct mode retains the last eight conversation messages.")
    if mcp:
        with st.expander("2. Available tools and retrieval outcomes", expanded=True):
            show_tool_outcomes(run)
            for step in run.get("mcp_trace", []):
                if step.get("step") == "MCP tools/list":
                    with st.expander("Discovered tool definitions"):
                        st.json(step.get("tools", []))
        with st.expander("3. Model requests and actual tool results"):
            for index, step in enumerate(run.get("mcp_trace", []), 1):
                if step.get("step") in {"Model tool selection", "MCP tools/call", "Rejected tool", "Failed tool call", "Gathering stopped", "Tool call limit reached", "Model turn limit reached"} and step.get("tool") != "server_info":
                    with st.expander(f"{index}. {step['step']} · {step.get('tool', '')}"):
                        st.json(step)
        with st.expander("4. Collected evidence"):
            show_mcp_summary(run)
    with st.expander("5. Final-generation request" if mcp else "2. Generation request"):
        st.markdown("**System message for answer generation**")
        messages = run.get("request", {}).get("messages", [])
        for message in messages:
            if message.get("role") == "system":
                st.code(message.get("content", ""), language="text")
        st.json(run.get("request", {}))
        if not run.get("generation_started", bool(run.get("response"))):
            st.warning("Final generation did not start; this is the last prepared request.")
    with st.expander("6. Answer, citations, and validation" if mcp else "3. Answer, citations, and validation", expanded=True):
        show_findings(run)
        st.write("Output schema: " + ("passed" if run.get("schema_valid") else "failed or not completed"))
        if run.get("checks"):
            st.json(run["checks"])
        if run.get("error"):
            st.error(run["error"])
        with st.expander("Raw model response"):
            st.json(run.get("response"))
    with st.expander("Context and token diagnostics · final generation"):
        show_request(run["request"], run.get("history_messages_dropped", 0), run.get("response"), mcp=mcp)
    with st.expander("Complete recorded run and protocol diagnostics"):
        st.json(run)
