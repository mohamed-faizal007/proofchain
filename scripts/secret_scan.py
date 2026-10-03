"""Scan the repository for committed secrets (P10-01). Stdlib only.

    python scripts/secret_scan.py            # scan tracked + untracked-not-ignored files
    python scripts/secret_scan.py --root DIR --no-git   # scan a plain directory (tests)

Exit code 1 when anything is found. Findings show file, line, rule and a redacted preview,
never the value. A real `.env` is gitignored so `git ls-files` never lists it, and this
script never opens a file named `.env*` other than `.env.example`.

Add `secret-scan: allow` in a comment on a line to suppress a deliberate fixture.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ALLOW_MARKER = "secret-scan: allow"
MAX_BYTES = 1_000_000
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".zip", ".pyc"}
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "artifacts", "cache", "dist"}

# Public keys every Hardhat install ships with (accounts #0-#2); not secrets.
HARDHAT_DEV_KEYS = {
    "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
}
PLACEHOLDER_WORDS = ("change-me", "changeme", "example", "placeholder", "your_", "your-", "xxxx")

# Variable-name hints for a wallet key; `pk` may sit between underscores (DEPLOYER_PK).
_NAMED_KEY = (
    r"(?:private[_-]?key|priv[_-]?key|(?<![a-z0-9])pk(?![a-z0-9])|deployer|signer|wallet"
    r"|signing[_-]?key|secret[_-]?key)"
)
_HEX64 = r"(?:0x)?[0-9a-fA-F]{64}"


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    preview: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.preview}"


def _entropy(value: str) -> float:
    counts = {c: value.count(c) for c in set(value)}
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values())


def _redact(value: str) -> str:
    return f"{value[:3]}...({len(value)} chars)"


def _is_placeholder(value: str) -> bool:
    low = value.lower()
    bare = low.removeprefix("0x")
    return (
        any(w in low for w in PLACEHOLDER_WORDS)
        or len(set(bare)) <= 2  # 111...1, 0xabab...
        or bare in HARDHAT_DEV_KEYS
        or low.startswith("test test test test")  # Hardhat's default mnemonic
        or low.endswith("example")
    )


def _looks_random(value: str) -> bool:
    has_digit = any(c.isdigit() for c in value)
    has_alpha = any(c.isalpha() for c in value)
    return (has_digit and has_alpha) or _entropy(value) >= 4.2


# (rule, regex, group holding the secret) -- evaluated per line.
_RULES: list[tuple[str, re.Pattern[str], int]] = [
    # NAME = 0x<64 hex>  (also YAML/JSON/TS object style, quoted or not)
    (
        "eth-private-key",
        re.compile(rf"(?i)[\w-]*{_NAMED_KEY}[\w-]*[\"']?\s*[=:]\s*[\"']?({_HEX64})\b"),
        1,
    ),
    # bare 0x<64 hex> only when the same line calls itself a private key / secret
    (
        "eth-private-key",
        re.compile(rf"(?i)(?:private\s+key|secret\s+key|privkey|signing\s+key)\D.*?\b(0x[0-9a-f]{{64}})\b"),
        1,
    ),
    ("pem-private-key", re.compile(r"(-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----)"), 1),
    # 12+ lowercase words after a mnemonic / seed-phrase name
    (
        "seed-phrase",
        re.compile(
            r"(?i)(?:mnemonic|seed[_ -]?phrase)\w*[\"']?\s*[=:]\s*[\"']?"
            r"((?:[a-z]{3,8}\s+){11,}[a-z]{3,8})"
        ),
        1,
    ),
    # key embedded in an RPC provider URL path
    (
        "rpc-provider-key",
        re.compile(
            r"(?:https?|wss?)://[\w.-]*(?:alchemy\.com|alchemyapi\.io|infura\.io|quiknode\.pro|ankr\.com)"
            r"/(?:[\w.-]+/)*([A-Za-z0-9_-]{24,})\b"
        ),
        1,
    ),
    # a key-looking value in a URL query string
    (
        "url-api-key",
        re.compile(r"[?&](?:api[-_]?key|apikey|access[-_]?token|token|key)=([A-Za-z0-9_-]{24,})"),
        1,
    ),
    # Etherscan-family keys are 34 chars of [A-Z0-9]
    (
        "etherscan-key",
        re.compile(
            r"(?i)(?:(?:etherscan|polygonscan|bscscan)\w*|apikey|api_key)[\"']?\s*[=:]\s*[\"']?"
            r"([A-Z0-9]{30,40})\b"
        ),
        1,
    ),
    (
        "vendor-token",
        re.compile(
            r"\b(ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}"
            r"|sk_live_[A-Za-z0-9]{16,}|xox[bpas]-[A-Za-z0-9-]{20,}|sk-ant-[A-Za-z0-9_-]{24,})"
        ),
        1,
    ),
    ("aws-access-key-id", re.compile(r"\b((?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[A-Z0-9]{16})\b"), 1),
    (
        "generic-secret",
        re.compile(
            r"(?i)\b[\w-]*(?:secret|password|passwd)[\w-]*[\"']?\s*[=:]\s*[\"']?"
            r"([A-Za-z0-9_+/=-]{16,})[\"']?"
        ),
        1,
    ),
    (
        "generic-secret",
        re.compile(
            r"(?i)\b[\w-]*(?:key|token)[\w-]*[\"']?\s*[=:]\s*[\"']?"
            r"([A-Za-z0-9_+/=-]{32,})[\"']?"
        ),
        1,
    ),
]


def scan_text(path: str, text: str) -> list[Finding]:
    found: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        seen: set[str] = set()
        for rule, pattern, group in _RULES:
            for m in pattern.finditer(line):
                value = m.group(group)
                if _is_placeholder(value) or value in seen:
                    continue
                if rule in {"generic-secret", "url-api-key"} and not _looks_random(value):
                    continue
                seen.add(value)
                found.append(Finding(path, lineno, rule, _redact(value)))
    return found


def scan_paths_by_name(paths: list[str]) -> list[Finding]:
    """A tracked `.env`/`.env.local` is a finding by itself; `.env.example` is the template."""
    out = []
    for p in paths:
        name = Path(p).name
        if name.startswith(".env") and name != ".env.example":
            out.append(Finding(p, 0, "dotenv-file-tracked", "real env file under version control"))
    return out


def _git_files(root: Path) -> list[str]:
    res = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [p for p in res.stdout.decode("utf-8", "replace").split("\0") if p]


def _walk_files(root: Path) -> list[str]:
    return [
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS)
    ]


def _skip(rel: str) -> bool:
    p = Path(rel)
    return (
        p.name in SKIP_NAMES
        or p.suffix.lower() in SKIP_SUFFIXES
        or bool(set(p.parts) & SKIP_DIRS)
        or (p.name.startswith(".env") and p.name != ".env.example")  # never open real env files
    )


def scan_repo(root: Path, use_git: bool = True) -> list[Finding]:
    rels = _git_files(root) if use_git else _walk_files(root)
    findings = scan_paths_by_name(rels)
    for rel in sorted(rels):
        if _skip(rel):
            continue
        path = root / rel
        try:
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue
        findings.extend(scan_text(rel, data.decode("utf-8", "replace")))
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--no-git", action="store_true", help="walk the directory instead of git")
    args = ap.parse_args(argv)
    findings = scan_repo(args.root, use_git=not args.no_git)
    for f in findings:
        print(f)
    if findings:
        print(f"\n{len(findings)} potential secret(s) found.", file=sys.stderr)
        return 1
    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
