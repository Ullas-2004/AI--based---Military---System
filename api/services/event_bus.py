"""In-process publish/subscribe bus backing the Server-Sent Events stream.

Deliberately simple: a bounded queue per subscriber, guarded by a lock. That is
the right shape for a single-process deployment.

SCALING NOTE
------------
This is per-process. Behind multiple workers (gunicorn -w 4) a client connected
to worker A will not see events published by worker B. Moving to Redis pub/sub
is a drop-in replacement for `publish`/`subscribe` when that day comes; the
route and the frontend do not change.
"""
import json
import logging
import queue
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Bounded so a stalled browser cannot grow memory without limit. When a
# subscriber falls this far behind, its oldest events are dropped rather than
# blocking the publisher — alerts are more useful fresh than complete.
MAX_QUEUE_SIZE = 100
MAX_SUBSCRIBERS = 50

_subscribers: set = set()
_lock = threading.Lock()


def subscribe() -> queue.Queue:
    """Register a new listener. Returns the queue to read events from."""
    listener: queue.Queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
    with _lock:
        if len(_subscribers) >= MAX_SUBSCRIBERS:
            logger.warning("Refusing SSE subscriber: %d already connected.", len(_subscribers))
            raise RuntimeError("Too many concurrent event subscribers.")
        _subscribers.add(listener)
        logger.info("SSE subscriber connected (%d active).", len(_subscribers))
    return listener


def unsubscribe(listener: queue.Queue) -> None:
    with _lock:
        _subscribers.discard(listener)
        logger.info("SSE subscriber disconnected (%d active).", len(_subscribers))


def subscriber_count() -> int:
    with _lock:
        return len(_subscribers)


def publish(event_type: str, payload: dict) -> None:
    """Broadcast an event to every connected listener. Never raises."""
    event = {
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    try:
        encoded = json.dumps(event, default=str)
    except (TypeError, ValueError):
        logger.exception("Could not serialise event %s", event_type)
        return

    with _lock:
        listeners = list(_subscribers)

    for listener in listeners:
        try:
            listener.put_nowait(encoded)
        except queue.Full:
            # Drop the oldest event and retry once, so a slow client degrades
            # to "most recent alerts" instead of stalling the publisher.
            try:
                listener.get_nowait()
                listener.put_nowait(encoded)
            except (queue.Empty, queue.Full):
                logger.debug("Dropping event for a saturated subscriber.")
