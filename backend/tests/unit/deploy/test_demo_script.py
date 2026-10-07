"""P10-04: static checks on scripts/demo.ps1 (no Docker needed).

The live behaviour is verified by running the script; these pin the decisions logged in
PROGRESS.md (NLP stays on, chain needs deploy + registry variables, no secrets, no .env reads).
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.deploy.script_loader import ROOT, load_script

DEMO_PS1 = ROOT / "scripts" / "demo.ps1"


@pytest.fixture(scope="module")
def text() -> str:
    return DEMO_PS1.read_text(encoding="utf-8")


def test_demo_never_passes_with_nlp_0(text: str) -> None:
    # The compose default (WITH_NLP=1) is what the demo needs; the script must not touch it.
    assert "WITH_NLP" not in text


def test_demo_starts_both_profiles_and_deploys(text: str) -> None:
    assert "--profile app" in text and "--profile chain" in text
    assert "hardhat run scripts/deploy.ts --network localhost" in text


def test_demo_passes_registry_vars_only_from_deploy_output(text: str) -> None:
    assert "$env:REGISTRY_ADDRESS" in text and "$env:ANCHOR_PRIVATE_KEY" in text
    secret_scan = load_script("secret_scan")
    for literal in re.findall(r"\b(?:0x)?[0-9a-fA-F]{64}\b", text):
        assert literal.removeprefix("0x").lower() in secret_scan.HARDHAT_DEV_KEYS


def test_demo_rebuilds_images_only_on_request(text: str) -> None:
    # A forced rebuild re-downloads the multi-GB NLP layers if the base image changed (live run).
    assert "[switch]$Build" in text
    assert not re.search(r"up -d[^\n]*--build", text)


def test_demo_port_check_understands_docker_port_ranges(text: str) -> None:
    # `docker ps` shows MinIO as 127.0.0.1:9000-9001->9000-9001/tcp (found in the live run).
    assert r"(?:-(\d+))?->" in text
    assert "$ours -notcontains $port" in text


def test_demo_never_reads_dot_env(text: str) -> None:
    assert not re.search(r"\.env\b(?!\.example)", text)


def test_demo_aborts_with_clear_message_if_chain_not_ready(text: str) -> None:
    assert "chain is not ready" in text
    assert re.search(r"throw .*chain is not ready", text)


def test_demo_refuses_to_reuse_a_stale_chain_without_reset(text: str) -> None:
    assert "-Reset" in text and "down -v" in text
    assert "eth_getCode" in text


def test_demo_sepolia_is_opt_in_and_takes_the_key_from_the_shell(text: str) -> None:
    assert "sepolia" in text
    assert "ValidateSet" in text  # -Network localhost|sepolia, localhost by default


@pytest.mark.skipif(
    shutil.which("powershell") is None and shutil.which("pwsh") is None,
    reason="PowerShell not installed",
)
def test_demo_script_parses_without_syntax_errors() -> None:
    exe = shutil.which("pwsh") or shutil.which("powershell")
    assert exe
    probe = (
        "$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{Path(DEMO_PS1)}',[ref]$null,[ref]$e);if($e){{$e|%{{$_.Message}};exit 1}}"
    )
    out = subprocess.run([exe, "-NoProfile", "-Command", probe], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
