"""Process-local shared request caps. No credentials or conversation text stored."""
from collections import deque
import hashlib
import threading
import time


class RequestBudgetExceeded(RuntimeError):
    status_code = 429


class RequestLimiter:
    def __init__(self, per_minute=20, per_day=200, clock=time.monotonic):
        self.per_minute, self.per_day, self.clock = per_minute, per_day, clock
        self.requests = {}
        self.lock = threading.Lock()

    def acquire(self, api_key):
        identity = hashlib.sha256(api_key.encode()).hexdigest()
        now = self.clock()
        with self.lock:
            queue = self.requests.setdefault(identity, deque())
            while queue and queue[0] <= now - 86400:
                queue.popleft()
            if len(queue) >= self.per_day or sum(t > now - 60 for t in queue) >= self.per_minute:
                raise RequestBudgetExceeded('Application request budget reached')
            queue.append(now)


SHARED_LIMITER = RequestLimiter()
