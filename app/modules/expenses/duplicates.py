"""KAN-34 duplicate confirmation metadata; committed retries live in the DB.

Only bounded navigation/identity metadata is kept in the signed session cookie.
The confirmation copies the authorized saved record, never a second raw form
payload. Database retry keys protect writes even after a cookie expires or two
workers receive the same confirmation at once.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import session

TOKEN_FIELD = "submission_token"
_PENDING_KEY = "expense_pending_duplicates"


def new_token():
    return secrets.token_urlsafe(24)


def _pending():
    raw = session.get(_PENDING_KEY, {})
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    return {key: value for key, value in raw.items()
            if isinstance(value, dict) and value.get("at", "") >= cutoff} if isinstance(raw, dict) else {}


def add_pending(*, flow, target, action, back, record_id, user_id):
    entries = _pending()
    pending_id = secrets.token_urlsafe(12)
    entries[pending_id] = dict(
        flow=flow, target=str(target), action=action, back=dict(back),
        record_id=str(record_id), user_id=str(user_id),
        at=datetime.now(timezone.utc).isoformat(),
    )
    session[_PENDING_KEY] = dict(sorted(entries.items(), key=lambda item: item[1]["at"])[-2:])
    return pending_id


def peek_pending(pending_id):
    return _pending().get(pending_id)


def take_pending(pending_id):
    entries = _pending()
    entry = entries.pop(pending_id, None)
    session[_PENDING_KEY] = entries
    return entry


def confirmation_token(pending_id, user_id):
    return hashlib.sha256(f"expense-copy:{user_id}:{pending_id}".encode()).hexdigest()
