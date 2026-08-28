"""A small in-process rate limiter for authentication endpoints.

Scope and limits, stated plainly: this is a per-process, in-memory counter.
It stops casual credential stuffing against a single instance, which is the
realistic threat for an app this size. It does NOT coordinate across
instances — scale the web service beyond one and each replica keeps its own
tally, so the effective limit multiplies by the replica count.

The correct fix at that point is a shared store (Redis) or a limiter at the
edge. Deliberately not pulled in here: it would mean adding infrastructure
for a single feature. Revisit when Redis arrives for caching anyway.
"""

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Allows `max_attempts` per `window_seconds`, per key.

    A sliding window rather than a fixed one: fixed windows let an attacker
    fire a full quota either side of a boundary and get double the attempts
    in an instant.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Records an attempt for `key`.

        Returns (allowed, seconds_until_retry). When allowed, the retry value
        is 0.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= self.max_attempts:
                retry_after = int(hits[0] + self.window_seconds - now) + 1
                return False, max(retry_after, 1)

            hits.append(now)
            return True, 0

    def reset(self, key: str) -> None:
        """Clears a key's history — call after a successful login so a user
        who simply mistyped their password isn't left throttled."""
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        """Drops all state. Used by tests."""
        with self._lock:
            self._hits.clear()

    def _prune(self, now: float) -> None:
        """Drops empty and fully-expired buckets.

        Without this the dict grows one entry per distinct key forever, which
        is a slow memory leak an attacker can drive by varying the email.
        """
        cutoff = now - self.window_seconds
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if not hits:
                del self._hits[key]

    def prune(self) -> None:
        with self._lock:
            self._prune(time.monotonic())
