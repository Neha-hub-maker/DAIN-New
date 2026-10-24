import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

from app.models.dain import MediaPackageStatus, ReviewDecision, SubmissionStatus, ValidationStatus


class CategoryFieldInput(BaseModel):
    field_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=200)
    field_type: str = Field(min_length=1, max_length=50)
    is_required: bool = False
    help_text: str | None = None
    options: dict[str, Any] | None = None
    display_order: int = 0


class CategoryCreateRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    fields: list[CategoryFieldInput] = Field(default_factory=list)


class CategoryFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field_key: str
    label: str
    field_type: str
    is_required: bool
    help_text: str | None
    options: dict[str, Any] | None
    display_order: int
    is_active: bool


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    is_active: bool
    field_definitions: list[CategoryFieldResponse]


class SubmissionFieldValueInput(BaseModel):
    field_definition_id: uuid.UUID
    value: dict[str, Any]


class SubmissionCreateRequest(BaseModel):
    category_id: uuid.UUID
    title: str = Field(min_length=3, max_length=250)
    summary: str = Field(min_length=20, max_length=10_000)
    achievement_date: date | None = None
    organization: str | None = Field(default=None, max_length=200)
    field_values: list[SubmissionFieldValueInput] = Field(default_factory=list)

    @field_validator("title", "summary")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value.strip()


class StoryVerificationRequest(BaseModel):
    """Accept form field names and their service-facing snake_case equivalents."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True, extra="forbid")

    headline: str = Field(min_length=10, max_length=120)
    summary: str = Field(min_length=30, max_length=600)
    sector: Literal["Academic", "Professional", "Entrepreneurial", "Social Impact", "Personal"] = Field(alias="category")
    classification: str = Field(alias="subType", min_length=1, max_length=120)
    institution: str = Field(min_length=1, max_length=200)
    primary_metric: str = Field(default="", alias="impact", max_length=200)
    evidence_link: HttpUrl | None = Field(default=None, alias="evidenceLink", max_length=2048)
    achievement_date: date = Field(alias="achievementDate")
    author_email: EmailStr = Field(alias="authorEmail", max_length=254)

    @field_validator("evidence_link", mode="before")
    @classmethod
    def empty_evidence_link_is_optional(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value


class StoryVerificationClaimResponse(BaseModel):
    text: str
    verdict: Literal["verified", "unverified", "contradicted"]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    sources: list[str]


class StoryVerificationStageResponse(BaseModel):
    id: Literal["identity", "editorial", "routing"]
    status: Literal["passed", "failed", "held", "skipped"]
    detail: str


class StoryVerificationResponse(BaseModel):
    status: Literal["verified", "needs_review", "rejected", "verification_pending"]
    reason: str
    claims: list[StoryVerificationClaimResponse] = Field(default_factory=list, max_length=4)
    stages: list[StoryVerificationStageResponse] = Field(min_length=3, max_length=3)


class SubmissionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=250)
    summary: str | None = Field(default=None, min_length=20, max_length=10_000)
    achievement_date: date | None = None
    organization: str | None = Field(default=None, max_length=200)
    field_values: list[SubmissionFieldValueInput] | None = None

    @field_validator("title", "summary")
    @classmethod
    def text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Value must not be blank.")
        return value.strip() if value is not None else None        


class SubmissionFieldValueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field_definition_id: uuid.UUID
    value: dict[str, Any]


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID
    category_id: uuid.UUID
    title: str
    summary: str
    achievement_date: date | None
    organization: str | None
    status: SubmissionStatus
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    field_values: list[SubmissionFieldValueResponse] = []


class MediaLinkCreateRequest(BaseModel):
    url: HttpUrl
    title: str | None = Field(default=None, max_length=255)
    link_type: str | None = Field(default=None, max_length=80)


class MediaLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    title: str | None
    link_type: str | None
    created_at: datetime


class MediaAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


class ReviewCreateRequest(BaseModel):
    decision: ReviewDecision
    notes: str | None = Field(default=None, max_length=5_000)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    reviewer_id: uuid.UUID
    decision: ReviewDecision
    notes: str | None
    created_at: datetime


class ValidationResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    check_type: str
    status: ValidationStatus
    details: dict[str, Any]
    checked_at: datetime


class SubmissionValidationResponse(BaseModel):
    submission_id: uuid.UUID
    results: list[ValidationResultResponse]


class MediaPackageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    slug: str
    status: MediaPackageStatus
    public_url: str | None
    generated_at: datetime | None
