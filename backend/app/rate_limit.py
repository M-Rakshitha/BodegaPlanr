from __future__ import annotations

import asyncio
import os
import time
from collections import deque


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = asyncio.Lock()
        self._request_times: deque[float] = deque()
        self._cooldown_until = 0.0

    async def acquire(self) -> None:
        while True:
            wait_seconds = 0.0
            async with self._lock:
                now = time.monotonic()

                while self._request_times and now - self._request_times[0] >= self.window_seconds:
                    self._request_times.popleft()

                cooldown_remaining = self._cooldown_until - now
                if cooldown_remaining > 0:
                    wait_seconds = max(wait_seconds, cooldown_remaining)

                if wait_seconds <= 0 and len(self._request_times) < self.max_requests:
                    self._request_times.append(now)
                    return

                if self._request_times:
                    oldest = self._request_times[0]
                    wait_seconds = max(wait_seconds, self.window_seconds - (now - oldest) + 0.01)

                wait_seconds = max(0.01, wait_seconds)

            await asyncio.sleep(wait_seconds)

    async def set_cooldown(self, seconds: float) -> None:
        if seconds <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            self._cooldown_until = max(self._cooldown_until, now + seconds)


def _read_rate_limit_per_minute(env_name: str, default_value: int = 13) -> int:
    raw = os.getenv(env_name, str(default_value)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default_value
    return max(1, min(13, value))


OUTBOUND_API_MAX_REQUESTS_PER_MINUTE = _read_rate_limit_per_minute("OUTBOUND_API_MAX_REQUESTS_PER_MINUTE", 13)
OUTBOUND_API_WINDOW_SECONDS = 60.0
GEMINI_MAX_REQUESTS_PER_MINUTE = _read_rate_limit_per_minute("GEMINI_MAX_REQUESTS_PER_MINUTE", 13)
GEMINI_WINDOW_SECONDS = 60.0

_outbound_limiter = SlidingWindowRateLimiter(
    max_requests=OUTBOUND_API_MAX_REQUESTS_PER_MINUTE,
    window_seconds=OUTBOUND_API_WINDOW_SECONDS,
)

_gemini_limiter = SlidingWindowRateLimiter(
    max_requests=GEMINI_MAX_REQUESTS_PER_MINUTE,
    window_seconds=GEMINI_WINDOW_SECONDS,
)


async def wait_for_outbound_slot() -> None:
    await _outbound_limiter.acquire()


async def wait_for_gemini_slot() -> None:
    await _gemini_limiter.acquire()


async def set_outbound_cooldown(seconds: float) -> None:
    await _outbound_limiter.set_cooldown(seconds)


async def set_gemini_cooldown(seconds: float) -> None:
    await _gemini_limiter.set_cooldown(seconds)
