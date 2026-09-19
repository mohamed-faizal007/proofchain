"""Exceptions raised by proofchain_core (02 §2). Mapped to API errors in the service layer."""


class ProofChainCoreError(Exception):
    """Base class for proofchain_core errors."""


class InvalidPdfError(ProofChainCoreError):
    """Input bytes are not a readable PDF."""


class EncryptedPdfError(ProofChainCoreError):
    """The PDF is encrypted (any encryption, including owner-only with no user password)."""


class NoExtractableTextError(ProofChainCoreError):
    """Fewer than 20 canonical characters in the whole document (likely scanned)."""
