"""Actual MCP stdio connection and bounded model-driven tool execution."""
import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from soc.core import SYSTEM

ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def connect(trace):
    params = StdioServerParameters(command=sys.executable, args=["-m", "soc.mcp_server"], cwd=str(ROOT))
    trace.append({"step": "Launch server", "client_pid": os.getpid(), "command": [params.command, *params.args], "transport": "stdio"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as session:
            initialized = await session.initialize()
            trace.append({"step": "MCP initialize", "result": initialized.model_dump(mode="json", by_alias=True)})
            tools = await session.list_tools()
            trace.append({"step": "MCP tools/list", "tools": [t.model_dump(mode="json", by_alias=True) for t in tools.tools]})
            try:
                yield session, tools.tools
            finally:
                trace.append({"step": "Close MCP session and stop child process"})


async def call(session, name, args, trace, source):
    started = time.perf_counter()
    result = await session.call_tool(name, args)
    trace.append({"step": "MCP tools/call", "source": source, "tool": name, "arguments": args,
                  "latency_s": round(time.perf_counter() - started, 3),
                  "result": result.model_dump(mode="json", by_alias=True)})
    data = result.structuredContent
    if data is None:
        text = "\n".join(c.text for c in result.content if c.type == "text")
        try:
            data = json.loads(text)
        except ValueError:
            data = {"text": text}
    return data, result.isError


async def demo_async(alert_id, trace):
    async with connect(trace) as (session, _):
        await call(session, "server_info", {}, trace, "App demo (no LLM)")
        alert, error = await call(session, "get_alert", {"alert_id": alert_id}, trace, "App demo (no LLM)")
        if not error:
            await call(session, "get_user", {"user_id": alert["user_id"]}, trace, "App demo (no LLM)")
            await call(session, "query_login_events", {"user_id": alert["user_id"]}, trace, "App demo (no LLM)")


def demo(alert_id):
    trace = []
    try:
        asyncio.run(asyncio.wait_for(demo_async(alert_id, trace), timeout=45))
    except Exception as exc:
        trace.append({"step": "Error", "error": str(exc)})
    return trace


async def gather(request, host, trace):
    """Starts with alert metadata only. Final structured generation occurs separately."""
    metadata = json.loads(request["messages"][1]["content"].split("\n", 1)[1])
    evidence = {"alert": request["messages"][1]["content"], "user": {}, "events": []}
    async with connect(trace) as (session, tools):
        await call(session, "server_info", {}, trace, "App process inspection")
        allowed = {t.name for t in tools if t.name != "server_info"}
        definitions = [{"type": "function", "function": {"name": t.name, "description": t.description,
                       "parameters": t.inputSchema}} for t in tools if t.name in allowed]
        messages = [dict(m) for m in request["messages"]]
        messages[0] = {"role": "system", "content": SYSTEM.replace("No tool access or live log access is available.", "Use the supplied tools to gather synthetic evidence. Fetch the user profile and timeline before answering. Do not invent tool results.")}
        calls = 0
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            for turn in range(4):
                payload = {"model": request["model"], "messages": messages, "tools": definitions,
                           "stream": False, "options": request["options"]}
                response = await client.post(host.rstrip("/") + "/api/chat", json=payload)
                response.raise_for_status()
                body = response.json()
                trace.append({"step": "Model tool selection", "turn": turn + 1, "request": payload, "response": body})
                message = body["message"]
                messages.append(message)
                requested = message.get("tool_calls") or []
                if not requested:
                    break
                for tool_call in requested:
                    if calls >= 6:
                        trace.append({"step": "Tool call limit reached", "limit": 6})
                        return evidence
                    calls += 1
                    function = tool_call["function"]
                    name, args = function["name"], function["arguments"]
                    scope_ok = (isinstance(args, dict) and
                                (args.get("alert_id") == metadata["alert_id"] if name == "get_alert"
                                 else args.get("user_id") == metadata["user_id"]))
                    if name not in allowed or not scope_ok:
                        data, error = {"error": "Unknown tool or arguments outside the selected alert scope"}, True
                        trace.append({"step": "Rejected tool", "tool": name, "arguments": args})
                    else:
                        data, error = await call(session, name, args, trace, "Model requested")
                    messages.append({"role": "tool", "tool_name": name, "content": json.dumps(data)})
                    if not error:
                        if name == "get_alert":
                            evidence["alert"] = data
                        elif name == "get_user":
                            evidence["user"] = data
                        elif name == "query_login_events":
                            evidence["events"] = data["events"]
            else:
                trace.append({"step": "Model turn limit reached", "limit": 4})
    return evidence


def gather_evidence(request, host, trace):
    return asyncio.run(asyncio.wait_for(gather(request, host, trace), timeout=240))
