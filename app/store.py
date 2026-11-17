"""Append-only JSON Lines logs: questions the bot could not answer, and leads."""

import json
import re
import threading
import time

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")


class JsonlLog:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    def append(self, record):
        record = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **record}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def read(self, limit=200):
        if not self.path.exists():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        rows = []
        for line in lines[-limit:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(rows))  # newest first


def unanswered_summary(rows):
    """Group unanswered questions (case-insensitive) with a count, most frequent first."""
    groups = {}
    for row in rows:
        key = " ".join(row.get("question", "").lower().split())
        if not key:
            continue
        g = groups.setdefault(key, {"question": row["question"], "count": 0, "last": row.get("ts")})
        g["count"] += 1
    return sorted(groups.values(), key=lambda g: (-g["count"], g["question"]))


def validate_lead(payload):
    """Return a clean lead dict or raise ValueError with a visitor-friendly message."""
    name = " ".join(str(payload.get("name", "")).split())[:100]
    email = str(payload.get("email", "")).strip()[:200]
    question = " ".join(str(payload.get("question", "")).split())[:500]
    if not name:
        raise ValueError("Please tell us your name.")
    if not EMAIL_RE.match(email):
        raise ValueError("Please enter a valid email address.")
    return {"name": name, "email": email, "question": question}
