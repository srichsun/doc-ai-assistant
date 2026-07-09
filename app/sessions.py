"""In-memory conversation store, keyed by session id.

Good enough for a demo; history resets when the process restarts. A real
deployment would back this with Redis or a database.
"""
_STORE: dict[str, list] = {}


def get(session_id: str) -> list:
    """Return the stored message history for a session (empty if new)."""
    return _STORE.get(session_id, [])


def save(session_id: str, messages: list) -> None:
    _STORE[session_id] = messages
