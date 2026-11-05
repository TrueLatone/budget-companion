"""Session-scoped anti-replay for expense creation forms.

No schema change and no field matching: each rendered form carries an opaque
token that the server remembers only after the write commits. Replaying a
remembered token opens a confirmation page instead of silently writing a
second identical transaction. Unknown or expired tokens fail open so ordinary
submissions are never rejected.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import session

TOKEN_FIELD = "submission_token"
_USED_KEY = "expense_used_tokens"
_PENDING_KEY = "expense_pending_duplicates"
_TOKEN_TTL = timedelta(minutes=60)
_PENDING_TTL = timedelta(minutes=60)
_MAX_USED = 6
_MAX_PENDING = 2


def new_token():
    return secrets.token_urlsafe(24)


def _now():
    return datetime.now(timezone.utc)


def _digest(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _fresh(entries, ttl):
    cutoff = (_now() - ttl).isoformat()
    return {
        key: value for key, value in entries.items()
        if isinstance(value, dict) and value.get("at", "") >= cutoff
    }


def _used():
    raw = session.get(_USED_KEY)
    return _fresh(raw, _TOKEN_TTL) if isinstance(raw, dict) else {}


def _pending():
    raw = session.get(_PENDING_KEY)
    return _fresh(raw, _PENDING_TTL) if isinstance(raw, dict) else {}


def _keep_newest(entries, limit):
    return dict(sorted(entries.items(), key=lambda item: item[1]["at"])[-limit:])


def remembered(token):
    """Return the committed write for this token, or None when unknown/expired."""
    if not token:
        return None
    return _used().get(_digest(token))


def remember(token, record_id, *, flow, target, user_id):
    """Mark a token as spent only after its write has committed."""
    if not token:
        return
    entries = _used()
    entries[_digest(token)] = {
        "record_id": str(record_id),
        "flow": flow,
        "target": str(target),
        "user_id": str(user_id),
        "at": _now().isoformat(),
    }
    session[_USED_KEY] = _keep_newest(entries, _MAX_USED)


def forget(token):
    if not token:
        return
    entries = _used()
    entries.pop(_digest(token), None)
    session[_USED_KEY] = entries


def add_pending(*, flow, target, payload, back, record_id, user_id):
    """Store one replay payload so the confirmation POST can re-run it once."""
    entries = _pending()
    pending_id = secrets.token_urlsafe(12)
    entries[pending_id] = {
        "flow": flow,
        "target": str(target),
        "payload": payload,
        "back": dict(back or {}),
        "record_id": str(record_id),
        "user_id": str(user_id),
        "at": _now().isoformat(),
    }
    session[_PENDING_KEY] = _keep_newest(entries, _MAX_PENDING)
    return pending_id


def peek_pending(pending_id):
    return _pending().get(pending_id)


def take_pending(pending_id):
    """Remove and return a pending replay; a second confirmation finds nothing."""
    entries = _pending()
    entry = entries.pop(pending_id, None)
    session[_PENDING_KEY] = entries
    return entry
