from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import User


class DuplicateEmailError(ValueError):
    """Raised when a normalized email already belongs to an account."""


def normalize_email(email):
    return email.strip().lower()


def register_user(email, password):
    user = User(
        email=normalize_email(email),
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise DuplicateEmailError from exc

    return user


def authenticate_user(email, password):
    normalized_email = normalize_email(email)
    user = db.session.scalar(db.select(User).where(User.email == normalized_email))

    if user is None or not user.is_active:
        return None
    if not check_password_hash(user.password_hash, password):
        return None
    return user
