"""Process-local rate limiting for paid verification requests."""

import math
from collections import deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, status


class IPRateLimiter:
    """Use a sliding window and expire inactive IPs; one instance per worker."""

    def __init__(self, limit: int = 5, window_seconds: float = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, ip: str) -> None:
        with self._lock:
            now = monotonic()
            for address in list(self._requests):
                requests = self._requests[address]
                while requests and requests[0] <= now - self.window_seconds:
                    requests.popleft()
                if not requests:
                    del self._requests[address]

            requests = self._requests.setdefault(ip, deque())
            if len(requests) >= self.limit:
                retry_after = max(1, math.ceil(requests[0] + self.window_seconds - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Story verification is limited to five requests per minute per IP.",
                    headers={"Retry-After": str(retry_after)},
                )
            requests.append(now)
