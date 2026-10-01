"""Small deterministic fixtures; expected verdicts never enter model context."""
SCENARIOS = {
    "Possible compromise": {
        "alert": "Repeated login failures followed by unfamiliar successful access",
        "user": {"id": "u-101", "name": "Alex Example", "usual_country": "US"},
        "events": [
            {"id": "e1", "time": "2026-09-30T08:00:00Z", "type": "login", "result": "failure", "country": "DE", "ip": "192.0.2.10", "attempts": 12},
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
        "alert": "Repeated failed logins",
        "user": {"id": "u-103", "name": "Lee Example", "usual_country": "US"},
        "events": [{"id": "e1", "time": "2026-09-30T10:00:00Z", "type": "login", "result": "failure", "attempts": 40, "ip": "198.51.100.20"}],
    },
    "Insufficient evidence": {
        "alert": "Unfamiliar login; incomplete telemetry",
        "user": {"id": "u-104", "name": "Pat Example"},
        "events": [{"id": "e1", "time": "2026-09-30T11:00:00Z", "type": "login", "result": "unknown", "country": "unknown"}],
    },
}
