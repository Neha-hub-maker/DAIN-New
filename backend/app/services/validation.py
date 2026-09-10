"""Explainable, deterministic validation for DAIN submissions."""

import re
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dain import (
    CategoryFieldDefinition,
    DuplicateMatch,
    DuplicateMatchStatus,
    Submission,
    SubmissionFieldValue,
    ValidationResult,
    ValidationStatus,
)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", value.lower())).strip()


def validate_completeness(database: Session, submission: Submission) -> ValidationResult:
    required_fields = database.scalars(
        select(CategoryFieldDefinition).where(
            CategoryFieldDefinition.category_id == submission.category_id,
            CategoryFieldDefinition.is_required.is_(True),
            CategoryFieldDefinition.is_active.is_(True),
        )
    ).all()
    supplied_ids = set(
        database.scalars(
            select(SubmissionFieldValue.field_definition_id).where(SubmissionFieldValue.submission_id == submission.id)
        ).all()
    )
    missing = [{"field_id": str(field.id), "field_key": field.field_key, "label": field.label} for field in required_fields if field.id not in supplied_ids]
    status = ValidationStatus.PASSED if not missing else ValidationStatus.WARNING
    result = ValidationResult(
        submission_id=submission.id,
        check_type="completeness",
        status=status,
        details={"missing_required_fields": missing},
    )
    database.add(result)
    return result


def detect_duplicates(database: Session, submission: Submission, threshold: float = 0.85) -> list[ValidationResult]:
    """Flag similar titles for human review; never reject a submission automatically."""
    source_title = normalize_text(submission.title)
    candidates = database.scalars(select(Submission).where(Submission.id != submission.id)).all()
    matches: list[dict[str, object]] = []
    for candidate in candidates:
        score = SequenceMatcher(None, source_title, normalize_text(candidate.title)).ratio()
        if score < threshold:
            continue
        match = database.scalar(
            select(DuplicateMatch).where(
                DuplicateMatch.source_submission_id == submission.id,
                DuplicateMatch.candidate_submission_id == candidate.id,
            )
        )
        if match is None:
            database.add(
                DuplicateMatch(
                    source_submission_id=submission.id,
                    candidate_submission_id=candidate.id,
                    similarity_score=score,
                    status=DuplicateMatchStatus.CANDIDATE,
                    match_details={"basis": "normalized_title_similarity"},
                )
            )
        matches.append({"submission_id": str(candidate.id), "similarity_score": round(score, 3)})
    result = ValidationResult(
        submission_id=submission.id,
        check_type="duplicate_detection",
        status=ValidationStatus.WARNING if matches else ValidationStatus.PASSED,
        details={"potential_matches": matches, "threshold": threshold},
    )
    database.add(result)
    return [result]
