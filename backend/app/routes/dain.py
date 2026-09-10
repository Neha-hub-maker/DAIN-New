"""Routes for DAIN submissions, review, validation, and packages."""

import uuid

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models.dain import (
    AchievementCategory,
    AuditLog,
    CategoryFieldDefinition,
    MediaAsset,
    MediaLink,
    MediaPackage,
    MediaPackageStatus,
    Review,
    ReviewDecision,
    Submission,
    SubmissionFieldValue,
    SubmissionStatus,
    User,
    UserRole,
    ValidationResult,
)
from app.routes.auth import get_current_verified_user, require_role
from app.schemas.auth import MessageResponse
from app.schemas.dain import (
    CategoryCreateRequest,
    CategoryResponse,
    MediaAssetResponse,
    MediaLinkCreateRequest,
    MediaLinkResponse,
    MediaPackageResponse,
    ReviewCreateRequest,
    ReviewResponse,
    SubmissionCreateRequest,
    SubmissionUpdateRequest,
    SubmissionResponse,
    SubmissionValidationResponse,
    ValidationResultResponse,
)
from app.services.media import media_root, render_media_package, save_upload
from app.services.validation import detect_duplicates, validate_completeness

router = APIRouter(tags=["dain"])


def _audit(
    database: Session,
    actor_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
) -> None:
    database.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details={},
        )
    )


def _submission_with_details(
    database: Session,
    submission_id: uuid.UUID,
) -> Submission:
    submission = database.scalar(
        select(Submission)
        .options(
            selectinload(Submission.field_values),
            selectinload(Submission.media_links),
            selectinload(Submission.media_assets),
        )
        .where(Submission.id == submission_id)
    )

    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found.",
        )

    return submission


def _can_access_submission(
    user: User,
    submission: Submission,
) -> bool:
    return (
        submission.author_id == user.id
        or user.role in {UserRole.EDITOR, UserRole.ADMIN}
    )


def _require_submission_access(
    user: User,
    submission: Submission,
) -> None:
    if not _can_access_submission(user, submission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this submission.",
        )


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories(
    database: Session = Depends(get_db),
    _: User = Depends(get_current_verified_user),
) -> list[AchievementCategory]:
    return (
        database.scalars(
            select(AchievementCategory)
            .options(selectinload(AchievementCategory.field_definitions))
            .where(AchievementCategory.is_active.is_(True))
            .order_by(AchievementCategory.name)
        )
        .unique()
        .all()
    )


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    payload: CategoryCreateRequest,
    database: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> AchievementCategory:
    if database.scalar(
        select(AchievementCategory).where(
            AchievementCategory.slug == payload.slug
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A category with this slug already exists.",
        )

    field_keys = [field.field_key for field in payload.fields]

    if len(field_keys) != len(set(field_keys)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Category field keys must be unique.",
        )

    category = AchievementCategory(
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
    )

    database.add(category)
    database.flush()

    for field in payload.fields:
        database.add(
            CategoryFieldDefinition(
                category_id=category.id,
                field_key=field.field_key,
                label=field.label,
                field_type=field.field_type,
                is_required=field.is_required,
                help_text=field.help_text,
                options=field.options,
                display_order=field.display_order,
            )
        )

    _audit(
        database,
        current_user.id,
        "category.created",
        "achievement_category",
        category.id,
    )

    database.commit()

    return _submission_category(database, category.id)


def _submission_category(
    database: Session,
    category_id: uuid.UUID,
) -> AchievementCategory:
    category = database.scalar(
        select(AchievementCategory)
        .options(selectinload(AchievementCategory.field_definitions))
        .where(AchievementCategory.id == category_id)
    )

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Achievement category not found.",
        )

    return category


@router.post(
    "/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_submission(
    payload: SubmissionCreateRequest,
    database: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
) -> Submission:
    category = _submission_category(database, payload.category_id)

    if not category.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This category is not accepting submissions.",
        )

    fields = {
        field.id: field
        for field in category.field_definitions
        if field.is_active
    }

    received_ids = [
        item.field_definition_id
        for item in payload.field_values
    ]

    if len(received_ids) != len(set(received_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each category field may be supplied only once.",
        )

    if any(field_id not in fields for field_id in received_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A supplied field does not belong to this category.",
        )

    submission = Submission(
        author_id=current_user.id,
        category_id=category.id,
        title=payload.title,
        summary=payload.summary,
        achievement_date=payload.achievement_date,
        organization=payload.organization.strip()
        if payload.organization
        else None,
    )

    database.add(submission)
    database.flush()

    for field_value in payload.field_values:
        database.add(
            SubmissionFieldValue(
                submission_id=submission.id,
                field_definition_id=field_value.field_definition_id,
                value=field_value.value,
            )
        )

    _audit(
        database,
        current_user.id,
        "submission.created",
        "submission",
        submission.id,
    )

    database.commit()

    return _submission_with_details(database, submission.id)


@router.get(
    "/submissions",
    response_model=list[SubmissionResponse],
)
def list_my_submissions(
    database: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
) -> list[Submission]:
    query = (
        select(Submission)
        .options(selectinload(Submission.field_values))
        .order_by(Submission.created_at.desc())
    )

    if current_user.role not in {UserRole.EDITOR, UserRole.ADMIN}:
        query = query.where(Submission.author_id == current_user.id)

    return database.scalars(query).unique().all()


@router.patch(
    "/submissions/{submission_id}",
    response_model=SubmissionResponse,
)
def update_submission(
    submission_id: uuid.UUID,
    payload: SubmissionUpdateRequest,
    database: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
) -> Submission:
    submission = _submission_with_details(database, submission_id)

    if submission.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the submission author may edit this submission.",
        )

    if submission.status not in {
        SubmissionStatus.DRAFT,
        SubmissionStatus.REQUIRES_CHANGES,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft or changes-requested submissions can be edited.",
        )

    if payload.title is not None:
        submission.title = payload.title

    if payload.summary is not None:
        submission.summary = payload.summary

    if payload.achievement_date is not None:
        submission.achievement_date = payload.achievement_date

    if payload.organization is not None:
        submission.organization = payload.organization.strip()

    if payload.field_values is not None:
        category = _submission_category(
            database,
            submission.category_id,
        )

        fields = {
            field.id: field
            for field in category.field_definitions
            if field.is_active
        }

        received_ids = [
            item.field_definition_id
            for item in payload.field_values
        ]

        if len(received_ids) != len(set(received_ids)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each category field may be supplied only once.",
            )

        if any(field_id not in fields for field_id in received_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A supplied field does not belong to this category.",
            )

        database.execute(
            delete(SubmissionFieldValue).where(
                SubmissionFieldValue.submission_id == submission.id
            )
        )

        for field_value in payload.field_values:
            database.add(
                SubmissionFieldValue(
                    submission_id=submission.id,
                    field_definition_id=field_value.field_definition_id,
                    value=field_value.value,
                )
            )

    _audit(
        database,
        current_user.id,
        "submission.updated",
        "submission",
        submission.id,
    )

    database.commit()

    return _submission_with_details(database, submission.id)


@router.get(
    "/submissions/{submission_id}",
    response_model=SubmissionResponse,
)
def get_submission(
    submission_id: uuid.UUID,
    database: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
) -> Submission:
    submission = _submission_with_details(database, submission_id)

    _require_submission_access(current_user, submission)

    return submission


@router.post(
    "/submissions/{submission_id}/submit",
    response_model=SubmissionValidationResponse,
)
def submit_submission(
    submission_id: uuid.UUID,
    database: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
) -> SubmissionValidationResponse:
    submission = _submission_with_details(database, submission_id)

    if submission.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the submission author may submit this story.",
        )

    if submission.status not in {
        SubmissionStatus.DRAFT,
        SubmissionStatus.REQUIRES_CHANGES,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This submission cannot be submitted in its current state.",
        )

    results = [
        validate_completeness(database, submission),
        *detect_duplicates(database, submission),
    ]

    submission.status = SubmissionStatus.SUBMITTED
    submission.submitted_at = datetime.now(timezone.utc)

    _audit(
        database,
        current_user.id,
        "submission.submitted",
        "submission",
        submission.id,
    )

    database.commit()

    for result in results:
        database.refresh(result)

    return SubmissionValidationResponse(
        submission_id=submission.id,
        results=[
            ValidationResultResponse.model_validate(result)
            for result in results
        ],
    )


@router.post(
    "/submissions/{submission_id}/links",
    response_model=MediaLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_media_link(
    submission_id: uuid.UUID,
    payload: MediaLinkCreateRequest,
    database: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
) -> MediaLink:
    submission = _submission_with_details(database, submission_id)

    if submission.author_id != current_user.id or submission.status not in {
        SubmissionStatus.DRAFT,
        SubmissionStatus.REQUIRES_CHANGES,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Links can only be added by the author while the "
                "submission is a draft or requires changes."
            ),
        )

    link = MediaLink(
        submission_id=submission.id,
        url=str(payload.url),
        title=payload.title,
        link_type=payload.link_type,
    )

    database.add(link)

    _audit(
        database,
        current_user.id,
        "submission.link_added",
        "submission",
        submission.id,
    )

    database.commit()
    database.refresh(link)

    return link


@router.post(
    "/submissions/{submission_id}/assets",
    response_model=MediaAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_asset(
    submission_id: uuid.UUID,
    file: UploadFile = File(...),
    database: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
) -> MediaAsset:
    submission = _submission_with_details(database, submission_id)

    if submission.author_id != current_user.id or submission.status not in {
        SubmissionStatus.DRAFT,
        SubmissionStatus.REQUIRES_CHANGES,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Files can only be added by the author while the "
                "submission is a draft or requires changes."
            ),
        )

    storage_key, original_filename, size_bytes = await save_upload(file)

    asset = MediaAsset(
        submission_id=submission.id,
        uploaded_by_id=current_user.id,
        original_filename=original_filename,
        storage_key=storage_key,
        content_type=file.content_type
        or "application/octet-stream",
        size_bytes=size_bytes,
    )

    database.add(asset)

    _audit(
        database,
        current_user.id,
        "submission.asset_uploaded",
        "submission",
        submission.id,
    )

    database.commit()
    database.refresh(asset)

    return asset


@router.get("/assets/{asset_id}")
def download_asset(
    asset_id: uuid.UUID,
    database: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
) -> FileResponse:
    asset = database.get(MediaAsset, asset_id)

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media asset not found.",
        )

    submission = _submission_with_details(
        database,
        asset.submission_id,
    )

    _require_submission_access(current_user, submission)

    path = media_root() / asset.storage_key

    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file is unavailable.",
        )

    return FileResponse(
        path,
        media_type=asset.content_type,
        filename=asset.original_filename,
    )


@router.get(
    "/editor/submissions",
    response_model=list[SubmissionResponse],
)
def review_queue(
    database: Session = Depends(get_db),
    _: User = Depends(
        require_role(UserRole.EDITOR, UserRole.ADMIN)
    ),
) -> list[Submission]:
    return (
        database.scalars(
            select(Submission)
            .options(selectinload(Submission.field_values))
            .where(
                Submission.status.in_(
                    [
                        SubmissionStatus.SUBMITTED,
                        SubmissionStatus.UNDER_REVIEW,
                    ]
                )
            )
            .order_by(Submission.submitted_at.asc())
        )
        .unique()
        .all()
    )

@router.post(
    "/submissions/{submission_id}/claim",
    response_model=SubmissionResponse,
)
def claim_submission(
    submission_id: uuid.UUID,
    database: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EDITOR, UserRole.ADMIN)),
) -> Submission:
    result = database.execute(
        update(Submission)
        .where(
            Submission.id == submission_id,
            Submission.status == SubmissionStatus.SUBMITTED,
            Submission.assigned_editor_id.is_(None),
        )
        .values(
            status=SubmissionStatus.UNDER_REVIEW,
            assigned_editor_id=current_user.id,
            review_started_at=datetime.now(timezone.utc),
        )
    )

    if result.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This submission is already under review or is not available.",
        )

    _audit(
        database,
        current_user.id,
        "submission.claimed",
        "submission",
        submission_id,
    )

    database.commit()

    return _submission_with_details(database, submission_id)

@router.post(
    "/submissions/{submission_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_review(
    submission_id: uuid.UUID,
    payload: ReviewCreateRequest,
    database: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.EDITOR, UserRole.ADMIN)
    ),
) -> Review:
    submission = _submission_with_details(
        database,
        submission_id,
    )

    if submission.status != SubmissionStatus.UNDER_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claim the submission before reviewing it.",
        )

    if submission.assigned_editor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This submission is assigned to another editor.",
        )

    status_by_decision = {
        ReviewDecision.APPROVED: SubmissionStatus.APPROVED,
        ReviewDecision.REJECTED: SubmissionStatus.REJECTED,
        ReviewDecision.REQUESTED_CHANGES: SubmissionStatus.REQUIRES_CHANGES,
    }

    review = Review(
        submission_id=submission.id,
        reviewer_id=current_user.id,
        decision=payload.decision,
        notes=payload.notes,
    )

    submission.status = status_by_decision[payload.decision]
    submission.assigned_editor_id = None
    submission.review_started_at = None

    database.add(review)

    _audit(
        database,
        current_user.id,
        f"submission.reviewed.{payload.decision.value}",
        "submission",
        submission.id,
    )

    database.commit()
    database.refresh(review)

    return review


@router.get(
    "/submissions/{submission_id}/validation",
    response_model=SubmissionValidationResponse,
)
def get_validation_results(
    submission_id: uuid.UUID,
    database: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
) -> SubmissionValidationResponse:
    submission = _submission_with_details(
        database,
        submission_id,
    )

    _require_submission_access(current_user, submission)

    results = database.scalars(
        select(ValidationResult)
        .where(ValidationResult.submission_id == submission.id)
        .order_by(ValidationResult.checked_at.desc())
    ).all()

    return SubmissionValidationResponse(
        submission_id=submission.id,
        results=[
            ValidationResultResponse.model_validate(result)
            for result in results
        ],
    )


@router.post(
    "/submissions/{submission_id}/media-package",
    response_model=MediaPackageResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_media_package(
    submission_id: uuid.UUID,
    database: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.EDITOR, UserRole.ADMIN)
    ),
) -> MediaPackage:
    submission = _submission_with_details(
        database,
        submission_id,
    )

    if submission.status != SubmissionStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only approved submissions can receive a media package.",
        )

    package = database.scalar(
        select(MediaPackage).where(
            MediaPackage.submission_id == submission.id
        )
    )

    if package is None:
        package = MediaPackage(
            submission_id=submission.id,
            slug=f"dain-{submission.id.hex}",
        )
        database.add(package)
        database.flush()

    package.status = MediaPackageStatus.GENERATING

    try:
        rendered_content = render_media_package(submission)

        storage_key = f"packages/{package.slug}.html"
        target = media_root() / storage_key

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            rendered_content,
            encoding="utf-8",
        )

        package.rendered_content = rendered_content
        package.storage_key = storage_key
        package.public_url = f"/packages/{package.slug}"
        package.generated_at = datetime.now(timezone.utc)
        package.status = MediaPackageStatus.GENERATED
        package.is_published = True

    except OSError:
        package.status = MediaPackageStatus.FAILED
        database.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The media package could not be generated.",
        )

    _audit(
        database,
        current_user.id,
        "media_package.generated",
        "media_package",
        package.id,
    )

    database.commit()
    database.refresh(package)

    return package


@router.post(
    "/submissions/{submission_id}/unpublish",
    response_model=MediaPackageResponse,
)
def unpublish_media_package(
    submission_id: uuid.UUID,
    database: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.EDITOR, UserRole.ADMIN)
    ),
) -> MediaPackage:
    package = database.scalar(
        select(MediaPackage).where(
            MediaPackage.submission_id == submission_id
        )
    )

    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media package not found.",
        )

    package.is_published = False

    _audit(
        database,
        current_user.id,
        "media_package.unpublished",
        "media_package",
        package.id,
    )

    database.commit()
    database.refresh(package)

    return package


def generate_media_package(
    submission_id: uuid.UUID,
    database: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.EDITOR, UserRole.ADMIN)
    ),
) -> MediaPackage:
    submission = _submission_with_details(
        database,
        submission_id,
    )

    if submission.status != SubmissionStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only approved submissions can receive a media package.",
        )

    package = database.scalar(
    select(MediaPackage).where(
        MediaPackage.slug == slug,
        MediaPackage.status == MediaPackageStatus.GENERATED,
        MediaPackage.is_published.is_(True),
    )
)

    if package is None:
        package = MediaPackage(
            submission_id=submission.id,
            slug=f"dain-{submission.id.hex}",
        )
        database.add(package)
        database.flush()

    package.status = MediaPackageStatus.GENERATING

    try:
        rendered_content = render_media_package(submission)

        storage_key = f"packages/{package.slug}.html"
        target = media_root() / storage_key

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered_content, encoding="utf-8")

        package.rendered_content = rendered_content
        package.storage_key = storage_key
        package.public_url = f"/packages/{package.slug}"
        package.generated_at = datetime.now(timezone.utc)
        package.status = MediaPackageStatus.GENERATED

    except OSError:
        package.status = MediaPackageStatus.FAILED
        database.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The media package could not be generated.",
        )

    _audit(
        database,
        current_user.id,
        "media_package.generated",
        "media_package",
        package.id,
    )

    database.commit()
    database.refresh(package)

    return package


@router.get(
    "/packages/{slug}",
    response_class=HTMLResponse,
    include_in_schema=True,
)
def view_media_package(
    slug: str,
    database: Session = Depends(get_db),
) -> HTMLResponse:
    package = database.scalar(
        select(MediaPackage).where(
            MediaPackage.slug == slug,
            MediaPackage.status == MediaPackageStatus.GENERATED,
        )
    )

    if package is None or not package.rendered_content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media package not found.",
        )

    return HTMLResponse(package.rendered_content)