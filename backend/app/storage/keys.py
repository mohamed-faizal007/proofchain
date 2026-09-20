"""Object keys (01_ARCHITECTURE.md §4)."""


def revision_key(document_id: str, revision_id: str) -> str:
    return f"documents/{document_id}/revisions/{revision_id}.pdf"
