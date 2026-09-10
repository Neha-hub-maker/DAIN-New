"""SQLAlchemy models for the DAIN MVP database schema."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, enum.Enum):
    USER = "user"
    EDITOR = "editor"
    ADMIN = "admin"


class SubmissionStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    REQUIRES_CHANGES = "requires_changes"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REQUESTED_CHANGES = "requested_changes"


class ValidationStatus(str, enum.Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class DuplicateMatchStatus(str, enum.Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class MediaPackageStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    GENERATED = "generated"
    FAILED = "failed"


class User(Base):
    """A DAIN member, editor, or administrator."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.USER)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    verification_tokens: Mapped[list["EmailVerificationToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    submissions: Mapped[list["Submission"]] = relationship(
    back_populates="author",
    foreign_keys="Submission.author_id",
    )
    uploaded_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="uploaded_by")
    reviews: Mapped[list["Review"]] = relationship(back_populates="reviewer")
    audit_entries: Mapped[list["AuditLog"]] = relationship(back_populates="actor")


class EmailVerificationToken(Base):
    """Hashed, one-time institutional-email verification token."""

    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="verification_tokens")


class AuthSession(Base):
    """Revocable session record that stores a token hash, never a raw token."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="sessions")


class AchievementCategory(Base):
    """A configurable achievement type that controls a dynamic submission form."""

    __tablename__ = "achievement_categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    field_definitions: Mapped[list["CategoryFieldDefinition"]] = relationship(back_populates="category", cascade="all, delete-orphan")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="category")


class CategoryFieldDefinition(Base):
    """One configurable question in a category's dynamic submission form."""

    __tablename__ = "category_field_definitions"
    __table_args__ = (UniqueConstraint("category_id", "field_key", name="uq_category_field_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("achievement_categories.id"), index=True)
    field_key: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(200))
    field_type: Mapped[str] = mapped_column(String(50))
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    category: Mapped["AchievementCategory"] = relationship(back_populates="field_definitions")
    values: Mapped[list["SubmissionFieldValue"]] = relationship(back_populates="field_definition")


class Submission(Base):
    """The main achievement or impact story supplied by a verified user."""

    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("achievement_categories.id"),
        index=True,
    )

    assigned_editor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    review_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(250),
        index=True,
    )

    summary: Mapped[str] = mapped_column(Text)

    achievement_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    organization: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(
            SubmissionStatus,
            name="submission_status",
        ),
        default=SubmissionStatus.DRAFT,
        index=True,
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    author: Mapped["User"] = relationship(
    back_populates="submissions",
    foreign_keys=[author_id],
    )

    category: Mapped["AchievementCategory"] = relationship(
        back_populates="submissions"
    )

    field_values: Mapped[list["SubmissionFieldValue"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )

    media_assets: Mapped[list["MediaAsset"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )

    media_links: Mapped[list["MediaLink"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )

    reviews: Mapped[list["Review"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )

    validation_results: Mapped[list["ValidationResult"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )

    duplicate_sources: Mapped[list["DuplicateMatch"]] = relationship(
        back_populates="source_submission",
        foreign_keys="DuplicateMatch.source_submission_id",
    )

    duplicate_candidates: Mapped[list["DuplicateMatch"]] = relationship(
        back_populates="candidate_submission",
        foreign_keys="DuplicateMatch.candidate_submission_id",
    )

    media_package: Mapped["MediaPackage | None"] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class SubmissionFieldValue(Base):
    """The answer to one dynamically defined category field."""

    __tablename__ = "submission_field_values"
    __table_args__ = (UniqueConstraint("submission_id", "field_definition_id", name="uq_submission_field_value"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    field_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("category_field_definitions.id"), index=True)
    value: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    submission: Mapped["Submission"] = relationship(back_populates="field_values")
    field_definition: Mapped["CategoryFieldDefinition"] = relationship(back_populates="values")


class MediaAsset(Base):
    """Metadata for a supporting upload; the binary is stored outside PostgreSQL."""

    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped["Submission"] = relationship(back_populates="media_assets")
    uploaded_by: Mapped["User"] = relationship(back_populates="uploaded_assets")


class MediaLink(Base):
    """A supporting external link, such as a publication or evidence URL."""

    __tablename__ = "media_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    link_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped["Submission"] = relationship(back_populates="media_links")


class Review(Base):
    """An editor's decision or feedback entry on a submitted story."""

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[ReviewDecision] = mapped_column(Enum(ReviewDecision, name="review_decision"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped["Submission"] = relationship(back_populates="reviews")
    reviewer: Mapped["User"] = relationship(back_populates="reviews")


class ValidationResult(Base):
    """Outcome of a completeness, duplicate, or future automated validation check."""

    __tablename__ = "validation_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    check_type: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[ValidationStatus] = mapped_column(Enum(ValidationStatus, name="validation_status"))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped["Submission"] = relationship(back_populates="validation_results")


class DuplicateMatch(Base):
    """A non-blocking potential duplicate pair identified by validation logic."""

    __tablename__ = "duplicate_matches"
    __table_args__ = (UniqueConstraint("source_submission_id", "candidate_submission_id", name="uq_duplicate_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    candidate_submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    similarity_score: Mapped[float] = mapped_column(Float)
    status: Mapped[DuplicateMatchStatus] = mapped_column(Enum(DuplicateMatchStatus, name="duplicate_match_status"), default=DuplicateMatchStatus.CANDIDATE)
    match_details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_submission: Mapped["Submission"] = relationship(back_populates="duplicate_sources", foreign_keys=[source_submission_id])
    candidate_submission: Mapped["Submission"] = relationship(back_populates="duplicate_candidates", foreign_keys=[candidate_submission_id])


class MediaPackage(Base):
    """A standardized, generated package for an approved submission."""

    __tablename__ = "media_packages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id"),
        unique=True,
    )
    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )
    status: Mapped[MediaPackageStatus] = mapped_column(
        Enum(MediaPackageStatus, name="media_package_status"),
        default=MediaPackageStatus.PENDING,
    )

    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    public_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    storage_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    rendered_content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    submission: Mapped["Submission"] = relationship(
        back_populates="media_package"
    )


class AuditLog(Base):
    """Minimal accountability record for sensitive authenticated or editorial actions."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(150), index=True)
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    actor: Mapped["User | None"] = relationship(back_populates="audit_entries")
