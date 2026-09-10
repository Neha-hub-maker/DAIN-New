"""Registration, institutional verification, login, and protected-account routes."""

import uuid
from app.services.email import send_verification_email
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.dain import AuditLog, AuthSession, EmailVerificationToken, User, UserRole
from app.schemas.auth import (
    EmailVerificationRequest,
    LoginRequest,
    MessageResponse,
    RegistrationRequest,
    RegistrationResponse,
    ResendVerificationRequest,
    TokenResponse,
    UserResponse,
)
from app.services.institutional_verification import institutional_verifier
from app.services.security import generate_token, hash_password, hash_token, session_expiry, utc_now, verification_expiry, verify_password


router = APIRouter(prefix="/auth", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)
INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired authentication credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _as_utc(value: datetime) -> datetime:
    """Treat a naive value from a development database as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _audit(database: Session, actor_id: uuid.UUID | None, action: str, entity_type: str, entity_id: uuid.UUID | None) -> None:
    database.add(AuditLog(actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id, details={}))


def _issue_verification_token(database: Session, user: User) -> str:
    raw_token = generate_token()
    database.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=verification_expiry(),
        )
    )
    return raw_token


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    database: Session = Depends(get_db),
) -> User:
    """Authenticate an opaque Bearer token and reject revoked/expired sessions."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise INVALID_CREDENTIALS

    session = database.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(credentials.credentials)))
    if session is None or session.revoked_at is not None or _as_utc(session.expires_at) <= utc_now():
        raise INVALID_CREDENTIALS

    user = session.user
    if user is None or not user.is_active:
        raise INVALID_CREDENTIALS
    return user


def get_current_verified_user(current_user: User = Depends(get_current_user)) -> User:
    """Authorization layer for DAIN actions that require institutional verification."""
    if not current_user.is_email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Institutional email verification is required.")
    return current_user


def require_role(*allowed_roles: UserRole):
    """Reusable authorization dependency for future editor/admin routes."""

    def verify_role(current_user: User = Depends(get_current_verified_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action.")
        return current_user

    return verify_role


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegistrationRequest, database: Session = Depends(get_db)) -> RegistrationResponse:
    """Create an unverified account and issue a one-time email-verification token."""
    email = str(payload.email).lower()
    if not institutional_verifier.accepts(email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A valid institutional email address is required.")
    if database.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        department=payload.department.strip() if payload.department else None,
    )
    database.add(user)
    database.flush()
    raw_token = _issue_verification_token(database, user)
    if not (
    settings.debug
    and settings.expose_verification_token_in_response
    ):
        send_verification_email(email, raw_token)
    _audit(database, user.id, "auth.registered", "user", user.id)
    database.commit()
    database.refresh(user)

    exposed_token = raw_token if settings.debug and settings.expose_verification_token_in_response else None
    return RegistrationResponse(
        user=UserResponse.model_validate(user),
        message="Registration accepted. Verify the institutional email before logging in.",
        verification_token=exposed_token,
    )


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: EmailVerificationRequest, database: Session = Depends(get_db)) -> MessageResponse:
    """Activate a user account after a valid, unused institutional-email token is supplied."""
    record = database.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token_hash == hash_token(payload.token)))
    if record is None or record.used_at is not None or _as_utc(record.expires_at) <= utc_now():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The verification token is invalid or expired.")

    record.used_at = utc_now()
    record.user.is_email_verified = True
    _audit(database, record.user_id, "auth.email_verified", "user", record.user_id)
    database.commit()
    return MessageResponse(message="Institutional email verified. You may now log in.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resend_verification(
    payload: ResendVerificationRequest,
    database: Session = Depends(get_db),
) -> MessageResponse:
    """Issue a replacement token without revealing whether an account exists."""
    email = str(payload.email).lower()
    user = database.scalar(select(User).where(User.email == email))

    if user is not None and not user.is_email_verified and user.is_active:
        raw_token = _issue_verification_token(database, user)

        if not (
            settings.debug
            and settings.expose_verification_token_in_response
        ):
            send_verification_email(email, raw_token)

        _audit(
            database,
            user.id,
            "auth.verification_resent",
            "user",
            user.id,
        )

    database.commit()

    return MessageResponse(
        message="If an eligible unverified account exists, a verification message will be sent."
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, database: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate a verified active user and issue one opaque Bearer token."""
    user = database.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise INVALID_CREDENTIALS
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is inactive.")
    if not user.is_email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verify your institutional email before logging in.")

    raw_token = generate_token()
    expires_at = session_expiry()
    database.add(AuthSession(user_id=user.id, token_hash=hash_token(raw_token), expires_at=expires_at))
    _audit(database, user.id, "auth.logged_in", "user", user.id)
    database.commit()
    return TokenResponse(access_token=raw_token, expires_at=expires_at, user=UserResponse.model_validate(user))


@router.post("/logout", response_model=MessageResponse)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> MessageResponse:
    """Revoke the current opaque token so it cannot be used again."""
    if credentials is None:
        raise INVALID_CREDENTIALS
    session = database.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(credentials.credentials)))
    if session is None:
        raise INVALID_CREDENTIALS
    session.revoked_at = utc_now()
    _audit(database, current_user.id, "auth.logged_out", "user", current_user.id)
    database.commit()
    return MessageResponse(message="Logged out successfully.")


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_verified_user)) -> User:
    """Return the authenticated verified DAIN account without exposing credentials."""
    return current_user
