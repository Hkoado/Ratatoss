"""In-process fixed-window rate limits for enrollment and pair claims."""

import math
import threading
from collections.abc import Callable, Hashable


class RateLimiter:
    """Allow `limit` hits per key in each window of `window_ms` milliseconds."""

    def __init__(self, *, limit: int, window_ms: int, clock: Callable[[], int]):
        if limit <= 0 or window_ms <= 0:
            raise ValueError("Rate limit and window must be positive")
        self._limit = limit
        self._window_ms = window_ms
        self._clock = clock
        self._lock = threading.Lock()
        self._start: int | None = None
        self._counts: dict[Hashable, int] = {}

    def hit(self, *keys: Hashable) -> int | None:
        """Count one request against every key. Return Retry-After seconds when over a limit."""
        now_ms = self._clock()
        start = now_ms - now_ms % self._window_ms
        with self._lock:
            if start != self._start:
                self._start, self._counts = start, {}
            counts = [self._counts.get(key, 0) + 1 for key in keys]
            self._counts.update(zip(keys, counts))
        if max(counts, default=0) > self._limit:
            return max(1, math.ceil((start + self._window_ms - now_ms) / 1000))
        return None
