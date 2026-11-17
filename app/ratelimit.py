"""Tiny in-memory sliding-window rate limiter (per visitor IP)."""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit, window_seconds, clock=time.monotonic):
        self.limit, self.window, self._clock = limit, window_seconds, clock
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key):
        """Record a hit and return (allowed, retry_after_seconds)."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(1, int(self.window - (now - hits[0])) + 1)
            hits.append(now)
            if len(self._hits) > 10_000:  # drop idle visitors so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True, 0
