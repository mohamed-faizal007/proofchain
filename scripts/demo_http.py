"""Tiny JSON/multipart HTTP client for scripts/demo_seed.py (stdlib only, P10-04).

`Api` is the seam: the demo logic talks to it, the script uses `UrllibApi`, tests use a
TestClient adapter. Paths are relative to the API prefix (e.g. "/auth/login").
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body: Any  # parsed JSON when the response is JSON, else raw bytes


class Api(Protocol):
    def call(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: Any = None,
        file: tuple[str, bytes] | None = None,
        fields: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> ApiResponse: ...


def multipart(file: tuple[str, bytes] | None, fields: dict[str, str] | None) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in (fields or {}).items():
        disposition = f'Content-Disposition: form-data; name="{name}"'
        parts.append(f"--{boundary}\r\n{disposition}\r\n\r\n{value}\r\n".encode())
    if file is not None:
        filename, data = file
        disposition = f'Content-Disposition: form-data; name="file"; filename="{filename}"'
        head = f"--{boundary}\r\n{disposition}\r\nContent-Type: application/pdf\r\n\r\n"
        parts.append(head.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class UrllibApi:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def call(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: Any = None,
        file: tuple[str, bytes] | None = None,
        fields: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> ApiResponse:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        data: bytes | None = None
        if file is not None or fields:
            data, headers["Content-Type"] = multipart(file, fields)
        elif json_body is not None:
            data, headers["Content-Type"] = json.dumps(json_body).encode(), "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:  # noqa: S310
                status, raw, ctype = resp.status, resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as err:
            status, raw, ctype = err.code, err.read(), err.headers.get("Content-Type", "")
        return ApiResponse(status, json.loads(raw) if "json" in ctype else raw)
