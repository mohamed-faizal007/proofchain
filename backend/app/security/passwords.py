"""Password hashing (bcrypt). Sync and CPU-bound: async callers use `anyio.to_thread`."""

import bcrypt

from app.errors import ValidationFailed

MAX_PASSWORD_BYTES = 72  # bcrypt ignores input beyond this; reject rather than truncate silently


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValidationFailed(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False
