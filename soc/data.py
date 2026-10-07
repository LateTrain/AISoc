"""Deterministic fixtures: each login event represents one attempt.

Alerts describe detection conditions; exact counts require querying individual events.
Existing IDs e1/e2/e3 are retained for the compromise's first failure/success/download.
"""
from datetime import datetime, timedelta, timezone


def failed_logins(count, start, ip, country=None, interval_seconds=10):
    records = []
    for index in range(count):
        record = {"id": "e1" if index == 0 else f"e{index + 3}",
                  "time": (start + timedelta(seconds=interval_seconds * index)).isoformat().replace("+00:00", "Z"),
                  "type": "login", "result": "failure", "ip": ip}
        if country:
            record["country"] = country
        records.append(record)
    return records


SCENARIOS = {
    "Possible compromise": {
        "alert": "Multiple failed logins within five minutes",
        "user": {"id": "u-101", "name": "Alex Example", "usual_country": "US"},
        "events": failed_logins(12, datetime(2026, 9, 30, 8, tzinfo=timezone.utc), "192.0.2.10", "DE") + [
            {"id": "e2", "time": "2026-09-30T08:03:00Z", "type": "login", "result": "success", "country": "DE", "ip": "192.0.2.10", "mfa": "unknown"},
            {"id": "e3", "time": "2026-09-30T08:06:00Z", "type": "download", "files": 240, "ip": "192.0.2.10"},
        ],
    },
    "Benign unusual login": {
        "alert": "Successful login from a new country",
        "user": {"id": "u-102", "name": "Sam Example", "usual_country": "US"},
        "events": [
            {"id": "e1", "time": "2026-09-30T09:00:00Z", "type": "login", "result": "success", "country": "CA", "mfa": "passed", "device": "known"},
            {"id": "e2", "time": "2026-09-29T12:00:00Z", "type": "travel_record", "destination": "CA", "approved": True},
        ],
    },
    "Failed attack": {
        "alert": "Multiple failed logins within five minutes",
        "user": {"id": "u-103", "name": "Lee Example", "usual_country": "US"},
        "events": failed_logins(40, datetime(2026, 9, 30, 10, tzinfo=timezone.utc), "198.51.100.20", interval_seconds=5),
    },
    "Insufficient evidence": {
        "alert": "Unfamiliar login; incomplete telemetry",
        "user": {"id": "u-104", "name": "Pat Example"},
        "events": [{"id": "e1", "time": "2026-09-30T11:00:00Z", "type": "login", "result": "unknown", "country": "unknown"}],
    },
}
