"""ID generation for module-owned entities.

Format: ``ddmmyyyy-uniqueid`` (see doc.md section 11.6 / doc-technical.md 9).
Only IDs owned by this module use this format. External M1 IDs are stored
verbatim and must never be reformatted.
"""

import re
import secrets
from datetime import date, datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))

# Strict pattern used for IDs produced by new_id() (8 date digits + 12 hex).
ID_PATTERN = r"^[0-9]{8}-[a-z0-9]{12}$"
ID_RE = re.compile(ID_PATTERN)

# Looser reference pattern from the specification.
ID_REFERENCE_PATTERN = r"^[0-9]{8}-[a-z0-9]{8,}$"
ID_REFERENCE_RE = re.compile(ID_REFERENCE_PATTERN)


def new_id(now: datetime | None = None) -> str:
    """Create a new module-owned ID using the creation date in Vietnam time."""
    now = now or datetime.now(VN_TZ)
    return f"{now:%d%m%Y}-{secrets.token_hex(6)}"


def is_valid_id(value: str | None) -> bool:
    """Return True when *value* matches the strict internal ID format."""
    return bool(value) and ID_RE.fullmatch(value) is not None


def creation_date(value: str) -> date | None:
    """Return the date encoded in an internal ID, or None if malformed.

    The encoded date is metadata only; business dates live in their own columns.
    """
    if not is_valid_id(value):
        return None
    try:
        return datetime.strptime(value[:8], "%d%m%Y").date()
    except ValueError:
        return None
