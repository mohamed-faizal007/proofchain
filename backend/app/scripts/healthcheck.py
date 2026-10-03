"""Container healthcheck: `python -m app.scripts.healthcheck [url]` (P10-03).

`GET /health` answers HTTP 200 even when degraded (04_API_SPEC), so the status code alone cannot
drive a Docker healthcheck. This exits 0 only when the body says `"status": "ok"`.
Stdlib only: the slim runtime image has no curl.
"""

import json
import sys
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000/api/v1/health"
DEFAULT_TIMEOUT_SECONDS = 5.0


def is_healthy(url: str = DEFAULT_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = json.loads(response.read())
    except (OSError, ValueError):  # refused, timeout, HTTP error (URLError/HTTPError), bad JSON
        return False
    return isinstance(body, dict) and body.get("status") == "ok"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    healthy = is_healthy(args[0]) if args else is_healthy()
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
