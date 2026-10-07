"""Synthetic MCP-only source. Never included in SCENARIOS/direct evidence."""
DEVICE_HISTORY = {
    "u-101": [{"id": "device-u101-1", "source": "device_history", "device_id": "unrecognized-browser", "familiar": False, "first_seen": "2026-09-30T08:03:00Z", "note": "No prior successful sessions recorded for this device in the 30-day history."}],
    "u-102": [{"id": "device-u102-1", "source": "device_history", "device_id": "managed-laptop-102", "familiar": True, "prior_successful_sessions": 27, "note": "Device matches the unfamiliar-location login and prior sessions."}],
    "u-103": [{"id": "device-u103-1", "source": "device_history", "device_id": "managed-laptop-103", "familiar": True, "note": "Known device history exists, but failed attempts supplied no device identifier; attribution is unavailable."}],
    "u-104": [{"id": "device-u104-1", "source": "device_history", "device_id": None, "familiar": None, "note": "Only one day of retention is available; device identity is missing. Familiarity cannot be established."}],
}
