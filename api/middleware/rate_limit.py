"""Sliding-window rate limiting for abuse-prone endpoints.

SCOPE
-----
State lives in this process. Behind multiple workers each holds its own
counters, so the effective limit is roughly ``limit x worker_count``. That is
acceptable for slowing credential stuffing on a single-node deployment and is
deliberately simple — swap the backing store for Redis (``INCR`` + ``EXPIRE``)
when you run more than one worker. The decorator signature does not change.

This is a speed bump, not a WAF. Put a real rate limiter at the edge for
anything internet-facing.
"""
import logging
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import jsonify, request

logger = logging.getLogger(__name__)

# ip -> deque of request timestamps within the window
_hits = defaultdict(deque)
_lock = threading.Lock()

# Stop unbounded growth from a spray of spoofed source addresses.
MAX_TRACKED_CLIENTS = 10_000


def _client_key() -> str:
    """Identify the caller.

    ``X-Forwarded-For`` is only consulted when a trusted proxy sets it. Behind
    an untrusted network it is caller-controlled and would let anyone evade the
    limit, so the direct peer address is the default.
    """
    return request.remote_addr or "unknown"


def _prune(bucket: deque, cutoff: float) -> None:
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def rate_limit(limit=None, window_seconds=None, scope: str = "",
               limit_key: str = None, window_key: str = None):
    """Allow at most ``limit`` requests per ``window_seconds`` per client.

    Pass ``limit_key``/``window_key`` to read the values from config at request
    time instead of hard-coding them, so limits stay tunable per environment.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from config import config
            if not config.RATE_LIMIT_ENABLED:
                return f(*args, **kwargs)

            effective_limit = getattr(config, limit_key) if limit_key else limit
            effective_window = getattr(config, window_key) if window_key else window_seconds

            key = f"{scope or f.__name__}:{_client_key()}"
            now = time.monotonic()
            cutoff = now - effective_window

            with _lock:
                if len(_hits) > MAX_TRACKED_CLIENTS:
                    # Cheap defence against memory growth: drop everything and
                    # start over rather than walking a huge dict on the hot path.
                    _hits.clear()
                    logger.warning("Rate-limit table cleared (tracking cap reached).")

                bucket = _hits[key]
                _prune(bucket, cutoff)

                if len(bucket) >= effective_limit:
                    retry_after = max(1, int(bucket[0] + effective_window - now) + 1)
                    logger.warning("Rate limit hit for %s on %s", _client_key(), request.path)
                    response = jsonify({
                        "status": "error",
                        "message": (
                            f"Too many requests. Try again in {retry_after} second(s)."
                        ),
                    })
                    response.status_code = 429
                    response.headers["Retry-After"] = str(retry_after)
                    return response

                bucket.append(now)
                remaining = effective_limit - len(bucket)

            result = f(*args, **kwargs)

            # Attach standard headers so clients can self-throttle.
            try:
                response = result[0] if isinstance(result, tuple) else result
                response.headers["X-RateLimit-Limit"] = str(effective_limit)
                response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
            except (AttributeError, IndexError, TypeError):
                pass
            return result
        return decorated
    return decorator


def reset() -> None:
    """Clear all counters. Used by tests."""
    with _lock:
        _hits.clear()
