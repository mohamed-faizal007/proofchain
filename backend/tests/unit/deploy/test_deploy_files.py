"""Static checks on the container setup (P10-03): compose `app` profile, Dockerfiles, env docs."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
COMPOSE = ROOT / "infra" / "docker-compose.yml"


@pytest.fixture(scope="module")
def services() -> dict[str, Any]:
    loaded = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return dict(loaded["services"])


def test_app_profile_has_backend_and_frontend(services: dict[str, Any]) -> None:
    for name in ("backend", "frontend"):
        assert services[name]["profiles"] == ["app"]


def test_infra_services_stay_in_default_profile(services: dict[str, Any]) -> None:
    for name in ("mongo", "minio", "minio-init"):
        assert "profiles" not in services[name]


def test_backend_uses_container_hostnames_not_localhost(services: dict[str, Any]) -> None:
    env = services["backend"]["environment"]
    assert env["MONGO_URI"].startswith("mongodb://mongo:")
    assert env["S3_ENDPOINT_URL"].startswith("http://minio:")
    assert "localhost" not in env["CHAIN_RPC_URL"] and "127.0.0.1" not in env["CHAIN_RPC_URL"]


def test_backend_waits_for_dependencies_and_bucket(services: dict[str, Any]) -> None:
    deps = services["backend"]["depends_on"]
    assert deps["mongo"]["condition"] == "service_healthy"
    assert deps["minio"]["condition"] == "service_healthy"
    assert deps["minio-init"]["condition"] == "service_completed_successfully"


def test_backend_healthcheck_parses_the_body(services: dict[str, Any]) -> None:
    """A bare HTTP-status check would stay green on a degraded /health (always 200)."""
    test = " ".join(services["backend"]["healthcheck"]["test"])
    assert "app.scripts.healthcheck" in test
    assert "curl" not in test


def test_backend_published_on_loopback_only(services: dict[str, Any]) -> None:
    for name in ("backend", "frontend"):
        assert all(p.startswith("127.0.0.1:") for p in services[name]["ports"])


def test_no_literal_secrets_in_compose(services: dict[str, Any]) -> None:
    env = services["backend"]["environment"]
    for key in ("JWT_SECRET", "SEED_PASSWORD", "ANCHOR_PRIVATE_KEY", "ANTHROPIC_API_KEY"):
        if key in env:
            assert str(env[key]).startswith("${"), key


def test_backend_cors_matches_published_frontend(services: dict[str, Any]) -> None:
    assert "http://localhost:8080" in services["backend"]["environment"]["CORS_ORIGINS"]
    assert any(":8080" in p for p in services["frontend"]["ports"])


@pytest.mark.parametrize("area", ["backend", "frontend"])
def test_dockerfile_runs_as_non_root(area: str) -> None:
    text = (ROOT / area / "Dockerfile").read_text(encoding="utf-8")
    users = re.findall(r"^USER\s+(\S+)", text, flags=re.MULTILINE)
    assert users and users[-1] not in {"root", "0"}


@pytest.mark.parametrize("area", ["backend", "frontend"])
def test_dockerignore_excludes_env_and_deps(area: str) -> None:
    lines = (ROOT / area / ".dockerignore").read_text(encoding="utf-8").split()
    for entry in (".env", "node_modules" if area == "frontend" else ".venv"):
        assert entry in lines or f"{entry}*" in lines or f"**/{entry}" in lines


def test_backend_image_nlp_is_a_build_arg_default_on() -> None:
    text = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^ARG WITH_NLP=1", text, flags=re.MULTILINE)


def test_compose_documents_every_new_env_var_in_env_example() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for var in re.findall(r"\$\{([A-Z_]+)[:?-]", COMPOSE.read_text(encoding="utf-8")):
        assert re.search(rf"^#?\s*{var}=", example, flags=re.MULTILINE), var


def test_backend_model_cache_is_readable_by_the_non_root_user() -> None:
    """The cache is written as root at build time; a 0600 file makes huggingface_hub log
    "corrupted tree cache" (Permission denied) on every start."""
    text = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "chmod -R a+rX /opt/hf" in text
