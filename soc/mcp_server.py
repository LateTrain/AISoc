"""A separate read-only tool-provider process. stdout belongs to MCP."""
import os

from mcp.server.fastmcp import FastMCP
from soc.data import SCENARIOS

mcp = FastMCP("AI SOC synthetic evidence")
ALERTS = {f"alert-{i}": data for i, data in enumerate(SCENARIOS.values(), 1)}


@mcp.tool()
def get_alert(alert_id: str) -> dict:
    """Fetch alert metadata and its affected user ID (no supporting events)."""
    if alert_id not in ALERTS:
        raise ValueError("Unknown alert ID")
    data = ALERTS[alert_id]
    return {"alert_id": alert_id, "alert": data["alert"], "user_id": data["user"]["id"]}


@mcp.tool()
def get_user(user_id: str) -> dict:
    """Fetch the synthetic user profile for a user ID."""
    for data in ALERTS.values():
        if data["user"]["id"] == user_id:
            return data["user"]
    raise ValueError("Unknown user ID")


@mcp.tool()
def query_login_events(user_id: str) -> dict:
    """Fetch the synthetic login investigation timeline, including related activity."""
    for data in ALERTS.values():
        if data["user"]["id"] == user_id:
            return {"user_id": user_id, "events": data["events"]}
    raise ValueError("Unknown user ID")


@mcp.tool()
def server_info() -> dict:
    """Show the server process identity for this learning lab."""
    return {"pid": os.getpid(), "transport": "stdio", "dataset": "synthetic"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
