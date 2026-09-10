"""Local MVP media storage and safe HTML package rendering."""

import html
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.models.dain import Submission


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def _matches_declared_type(data: bytes, content_type: str) -> bool:
    signatures = {
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        "application/pdf": data.startswith(b"%PDF-"),
    }
    return signatures.get(content_type, False)


def media_root() -> Path:
    root = Path(settings.media_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


async def save_upload(upload: UploadFile) -> tuple[str, str, int]:
    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only JPEG, PNG, WEBP, and PDF uploads are allowed.")
    data = await upload.read(settings.max_upload_size_bytes + 1)
    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The uploaded file is empty.")
    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="The uploaded file exceeds the configured size limit.")
    if not _matches_declared_type(data, upload.content_type):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The file contents do not match its declared type.")
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}[upload.content_type]
    storage_key = f"assets/{uuid.uuid4().hex}{extension}"
    target = media_root() / storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return storage_key, upload.filename or "upload", len(data)


def render_media_package(submission: Submission) -> str:
    title = html.escape(submission.title)
    summary = "<br>".join(html.escape(submission.summary).splitlines())
    organization = html.escape(submission.organization or "DUNITE community")
    links = "".join(
        f'<li><a href="{html.escape(link.url, quote=True)}" rel="noopener noreferrer">{html.escape(link.title or link.url)}</a></li>'
        for link in submission.media_links
    ) or "<li>No supporting links provided.</li>"
    return f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{title} | DAIN</title>
<style>body{{font-family:Arial,sans-serif;line-height:1.6;max-width:760px;margin:48px auto;padding:0 24px;color:#172033}}h1{{line-height:1.2}}.meta{{color:#52606d}}</style></head>
<body><p class=\"meta\">DAIN media-ready story package</p><h1>{title}</h1><p class=\"meta\">{organization}</p><p>{summary}</p><h2>Supporting links</h2><ul>{links}</ul></body></html>"""
