"""Small local-only JSON-lines database stored in a .txt file."""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

FILE_PATH = Path(__file__).resolve().parent / "data" / "budgets.txt"
_LOCK = threading.Lock()


def save_event(event_type, payload):
    FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    item = {
        "id": uuid4().hex,
        "event_type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    with _LOCK:
        with FILE_PATH.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return item["id"]


def find_event(event_id, event_type):
    if not FILE_PATH.exists():
        return None
    # Fine for a small class prototype; a real app should use a database.
    with _LOCK:
        with FILE_PATH.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("id") == event_id and record.get("event_type") == event_type:
                    return record
    return None


def recent_confirmed(limit=10):
    if not FILE_PATH.exists():
        return []
    with _LOCK:
        with FILE_PATH.open(encoding="utf-8") as stream:
            results = []
            for line in stream:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("event_type") == "confirmed":
                    results.append({"id": item["id"], "date": item["created_at"],
                                    "month": item["data"]["month"],
                                    "plan": item["data"]["plan"]["name"],
                                    "total": item["data"]["available_funds"]})
    return results[-limit:][::-1]
