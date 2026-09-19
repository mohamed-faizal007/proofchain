"""Domain exceptions, mapped to the error envelope in docs/04_API_SPEC.md."""

from typing import Any


class DomainError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class ValidationFailed(DomainError):
    code = "VALIDATION_ERROR"
    status_code = 422


class InvalidPdfError(DomainError):
    code = "INVALID_PDF"
    status_code = 422


class EncryptedPdfError(DomainError):
    code = "ENCRYPTED_PDF"
    status_code = 422


class NoExtractableTextError(DomainError):
    code = "NO_EXTRACTABLE_TEXT"
    status_code = 422


class FileTooLargeError(DomainError):
    code = "FILE_TOO_LARGE"
    status_code = 413


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    status_code = 404


class ForbiddenError(DomainError):
    code = "FORBIDDEN"
    status_code = 403


class SelfApprovalForbiddenError(DomainError):
    code = "SELF_APPROVAL_FORBIDDEN"
    status_code = 403


class RevisionNotPendingError(DomainError):
    code = "REVISION_NOT_PENDING"
    status_code = 409


class PendingRevisionExistsError(DomainError):
    code = "PENDING_REVISION_EXISTS"
    status_code = 409


class NoContentChangeError(DomainError):
    code = "NO_CONTENT_CHANGE"
    status_code = 409


class AnchorFailedError(DomainError):
    code = "ANCHOR_FAILED"
    status_code = 502


class ChainUnavailableError(DomainError):
    code = "CHAIN_UNAVAILABLE"
    status_code = 503
