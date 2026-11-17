"""Short-term conversation memory so visitors can ask follow-up questions.

Each browser tab gets a random session id; we keep its last few turns in RAM
(nothing is written to disk) and forget idle sessions after 30 minutes.
"""

import re
import secrets
import threading
import time
from collections import OrderedDict, deque

MAX_TURNS = 6
TTL_SECONDS = 30 * 60
MAX_SESSIONS = 2000
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# Pronouns that point back at the previous topic ("how much is it?", "do they open Saturday?").
FOLLOW_UP_RE = re.compile(r"\b(it|its|that|this|those|these|they|them|one)\b", re.I)


class ConversationMemory:
    def __init__(self, max_turns=MAX_TURNS, ttl=TTL_SECONDS, max_sessions=MAX_SESSIONS, clock=time.monotonic):
        self._sessions = OrderedDict()
        self._lock = threading.Lock()
        self.max_turns, self.ttl, self.max_sessions, self._clock = max_turns, ttl, max_sessions, clock

    @staticmethod
    def normalise_id(session_id):
        return session_id if session_id and SESSION_RE.match(session_id) else secrets.token_urlsafe(12)

    def history(self, session_id):
        with self._lock:
            self._expire()
            entry = self._sessions.get(session_id)
            return list(entry[1]) if entry else []

    def add(self, session_id, question, answer, topic=""):
        with self._lock:
            entry = self._sessions.pop(session_id, None)
            turns = entry[1] if entry else deque(maxlen=self.max_turns)
            turns.append({"q": question, "a": answer, "topic": topic})
            self._sessions[session_id] = (self._clock(), turns)
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)

    def _expire(self):
        now = self._clock()
        for sid in [sid for sid, (seen, _) in self._sessions.items() if now - seen > self.ttl]:
            del self._sessions[sid]


def looks_like_follow_up(question):
    """A question that refers back to the previous turn ('how much is it?')."""
    return bool(FOLLOW_UP_RE.search(question))
