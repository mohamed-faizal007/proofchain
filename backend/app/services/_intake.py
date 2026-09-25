"""Upload validation and tree building shared by registration and revision submission."""

from pathlib import PurePosixPath, PureWindowsPath

import anyio.to_thread

from app.errors import (
    EncryptedPdfError,
    FileTooLargeError,
    InvalidPdfError,
    NoExtractableTextError,
    ValidationFailed,
)
from proofchain_core import build_integrity_tree
from proofchain_core import errors as core_errors
from proofchain_core.types import IntegrityTree

MAX_NOTE_CHARS = 2000
MAX_FILENAME_CHARS = 255


def clean_filename(name: str | None) -> str:
    base = PurePosixPath(PureWindowsPath(name or "").name).name.strip()
    return (base or "document.pdf")[:MAX_FILENAME_CHARS]


def clean_note(change_note: str | None) -> str | None:
    note = (change_note or "").strip() or None
    if note and len(note) > MAX_NOTE_CHARS:
        raise ValidationFailed(f"change_note must be at most {MAX_NOTE_CHARS} characters")
    return note


async def build_tree_from_upload(data: bytes, max_bytes: int) -> IntegrityTree:
    if len(data) > max_bytes:
        raise FileTooLargeError("File exceeds the upload limit", details={"max_bytes": max_bytes})
    if b"%PDF-" not in data[:1024]:
        raise InvalidPdfError("File is not a PDF")
    try:
        return await anyio.to_thread.run_sync(build_integrity_tree, data)
    except core_errors.EncryptedPdfError as exc:
        raise EncryptedPdfError("PDF is encrypted") from exc
    except core_errors.NoExtractableTextError as exc:
        raise NoExtractableTextError("PDF has no extractable text") from exc
    except core_errors.InvalidPdfError as exc:
        raise InvalidPdfError("File is not a readable PDF") from exc
