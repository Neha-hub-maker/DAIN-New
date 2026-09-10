"""Password and opaque session-token primitives used by authentication routes."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings

try:
    from pwdlib import PasswordHash
    password_hash = PasswordHash.recommended()

    def hash_password(password: str) -> str:
        return password_hash.hash(password)

    def verify_password(password: str, hashed_password: str) -> bool:
        return password_hash.verify(password, hashed_password)
except ImportError:
    import hmac

    def hash_password(password: str) -> str:
        salt = secrets.token_hex(16)
        hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return f"sha256:{salt}:{hashed}"

    def verify_password(password: str, hashed_password: str) -> bool:
        if not hashed_password.startswith("sha256:"):
            return False
        parts = hashed_password.split(":")
        if len(parts) != 3:
            return False
        salt, expected = parts[1], parts[2]
        computed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return hmac.compare_digest(computed, expected)


def generate_token() -> str:
    """Generate a high-entropy opaque token safe to send to a client once."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Create a deterministic database-safe representation of an opaque token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def verification_expiry() -> datetime:
    return utc_now() + timedelta(minutes=settings.verification_token_ttl_minutes)


def session_expiry() -> datetime:
    return utc_now() + timedelta(minutes=settings.session_token_ttl_minutes)
