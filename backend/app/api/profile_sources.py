"""Profile source ingestion API (ADR-011 §8): upload, list, review, reparse, download, delete.

Auth (401) and CSRF (403) are enforced by `require_owner` on the private router (app.main).
Errors never echo file content or extracted text.
"""

import urllib.parse
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.deps import DbSession
from app.profile.resume_parser import (
    APPLICATION_PDF,
    MAX_UPLOAD_BYTES,
    TEXT_PLAIN,
    UnreadableFile,
    UnsupportedFileType,
)
from app.schemas.profile_source import (
    DeleteResponse,
    ProfileSourceDetail,
    ProfileSourceSummary,
    ReviewRequest,
    ReviewResponse,
)
from app.services import profile_sources as service

router = APIRouter(prefix="/profile/sources", tags=["profile-sources"])

# Content-Length is checked against this before any multipart parsing happens, to allow for
# boundary/header overhead around the actual file bytes (ADR-011 §2).
MULTIPART_OVERHEAD = 64 * 1024
CHUNK_SIZE = 64 * 1024
EXTENSIONS = {TEXT_PLAIN: ".txt", APPLICATION_PDF: ".pdf"}


def _load(db: DbSession, source_id: uuid.UUID) -> service.ProfileSource:
    source = service.get_source(db, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found.")
    return source


@router.get("")
def list_sources(db: DbSession) -> list[ProfileSourceSummary]:
    return service.list_sources(db)


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_source(request: Request, db: DbSession) -> ProfileSourceDetail:
    # Checked from the header alone, before touching the body: a lying Content-Length is
    # rejected even if the actual body never arrives.
    content_length = request.headers.get("content-length")
    try:
        length = int(content_length) if content_length is not None else None
    except ValueError:
        length = None
    if length is None:
        raise HTTPException(status.HTTP_411_LENGTH_REQUIRED, "Content-Length is required.")
    if length > MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "That file is larger than 2 MB.")

    # One file field and nothing else.
    form = await request.form(
        max_files=1, max_fields=0, max_part_size=MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD
    )
    try:
        upload = form.get("file")
        if not isinstance(upload, StarletteUploadFile):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No file uploaded.")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await upload.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE, "That file is larger than 2 MB."
                )
            chunks.append(chunk)
        data = b"".join(chunks)
        filename = upload.filename
    finally:
        await form.close()

    # Parsing (up to PDF_TIMEOUT_SECONDS) and database work are blocking: keep them off the event
    # loop so the single worker still serves other requests meanwhile.
    try:
        detail = await run_in_threadpool(service.create_source, db, data, filename)
    except UnsupportedFileType as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except UnreadableFile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except service.DuplicateSource as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await run_in_threadpool(db.commit)
    return detail


@router.get("/{source_id}")
def get_source_detail(source_id: uuid.UUID, db: DbSession) -> ProfileSourceDetail:
    source = _load(db, source_id)
    return service.source_detail(db, source)


@router.get("/{source_id}/file")
def download_source(source_id: uuid.UUID, db: DbSession) -> Response:
    source = _load(db, source_id)
    content = service.artifact_bytes(db, source_id)
    if content is None:  # pragma: no cover - the artifact always exists with its source
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found.")

    media_type = (
        "text/plain; charset=utf-8"
        if source.content_type == TEXT_PLAIN
        else (source.content_type or "application/octet-stream")
    )
    name = (
        source.original_filename or f"profile-source{EXTENSIONS.get(source.content_type or '', '')}"
    )
    ascii_name = "".join(ch if 32 <= ord(ch) < 127 and ch not in '"\\' else "_" for ch in name)
    encoded_name = urllib.parse.quote(name, safe="")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.post("/{source_id}/review")
def review_source(source_id: uuid.UUID, body: ReviewRequest, db: DbSession) -> ReviewResponse:
    source = _load(db, source_id)
    try:
        result = service.review_source(db, source, body)
    except service.FactNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except service.InvalidReview as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.commit()
    return result


@router.post("/{source_id}/reparse")
def reparse_source(source_id: uuid.UUID, db: DbSession) -> ProfileSourceDetail:
    source = _load(db, source_id)
    try:
        detail = service.reparse_source(db, source)
    except (UnsupportedFileType, UnreadableFile) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.commit()
    return detail


@router.delete("/{source_id}")
def delete_source(source_id: uuid.UUID, db: DbSession) -> DeleteResponse:
    source = _load(db, source_id)
    result = service.delete_source(db, source)
    db.commit()
    return result
