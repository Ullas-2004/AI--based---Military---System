"""Server-Sent Events endpoint for live operational alerts."""
import logging
import queue

from flask import Blueprint, Response, jsonify, request, stream_with_context

from middleware.auth import decode_token
from services import event_bus

logger = logging.getLogger(__name__)
stream_bp = Blueprint("stream", __name__)

# If no event arrives within this window, emit a comment frame. That keeps
# proxies and load balancers from closing an idle connection.
#
# It also bounds how long a dead connection lingers: under WSGI the generator
# only learns the client vanished when a write fails, so a disconnected
# subscriber is reclaimed on the next heartbeat rather than immediately. Keep
# this low enough that reconnect churn cannot exhaust MAX_SUBSCRIBERS.
HEARTBEAT_SECONDS = 15


@stream_bp.route("/alerts", methods=["GET"])
def alert_stream():
    """Stream operational alerts to the browser.

    EventSource cannot set an Authorization header, so the token is accepted as
    a query parameter here. That is a deliberate, contained exception: the
    endpoint is read-only, the token is still fully verified, and it is never
    logged (see the access-log filter in app.py).
    """
    token = request.args.get("token", "")
    if not token:
        return jsonify({
            "status": "error",
            "message": "Authentication required. Pass ?token=<jwt>.",
        }), 401

    claims = decode_token(token)
    if "error" in claims:
        return jsonify({"status": "error", "message": claims["error"]}), 401

    try:
        listener = event_bus.subscribe()
    except RuntimeError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503

    @stream_with_context
    def generate():
        try:
            # Tell the client we are live before any real event arrives.
            yield 'event: connected\ndata: {"status":"connected"}\n\n'
            while True:
                try:
                    payload = listener.get(timeout=HEARTBEAT_SECONDS)
                    yield f"data: {payload}\n\n"
                except queue.Empty:
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            # Normal disconnect: the browser navigated away or closed.
            raise
        finally:
            event_bus.unsubscribe(listener)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@stream_bp.route("/status", methods=["GET"])
def stream_status():
    """How many live listeners are attached. Useful for demos and debugging."""
    return jsonify({
        "status": "success",
        "subscribers": event_bus.subscriber_count(),
    }), 200
