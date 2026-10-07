"""Summarize recorded outcomes, including legacy runs, without assuming success."""
import json


def summarize_mcp(run):
    success, problems, inspection = [], [], []
    recovered = {}
    for entry in run.get("mcp_trace", []):
        tool = entry.get("tool")
        if tool == "server_info":
            inspection.append(entry)
            continue
        if entry.get("step") in {"Rejected tool", "Failed tool call"}:
            problems.append(entry)
        if entry.get("step") != "MCP tools/call" or entry.get("source") != "Model requested":
            continue
        result = entry.get("result", {})
        if result.get("isError") is not False:
            problems.append(entry)
            continue
        success.append({"tool": tool, "arguments": entry.get("arguments", {}), "latency_s": entry.get("latency_s")})
        data = result.get("structuredContent")
        if data is None:
            try:
                data = json.loads("\n".join(c["text"] for c in result.get("content", []) if c.get("type") == "text"))
            except (ValueError, KeyError):
                continue
        key = {"get_alert": "alert", "get_user": "user", "query_login_events": "events", "get_device_history": "device_history"}.get(tool)
        if key:
            recovered[key] = data if key in {"user", "alert"} else data.get(key, [])
    evidence = run.get("evidence_collected") or recovered
    warnings = []
    if not evidence.get("events"):
        warnings.append("No event timeline was collected.")
    if not evidence.get("user"):
        warnings.append("No user profile was collected.")
    if problems:
        warnings.append("Some tool calls were rejected or failed; review the recorded outcomes.")
    if run.get("error"):
        warnings.append("The run stopped with an error: " + run["error"])
    if any(s.get("step") in {"Tool call limit reached", "Model turn limit reached"} for s in run.get("mcp_trace", [])):
        warnings.append("Gathering reached an execution limit.")
    return {"successful_calls": success, "problems": problems, "inspection": inspection,
            "evidence": evidence, "event_count": len(evidence.get("events", [])),
            "user_fetched": bool(evidence.get("user")), "device_count": len(evidence.get("device_history", [])),
            "device_called": any(s["tool"] == "get_device_history" for s in success), "warnings": warnings}
