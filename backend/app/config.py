"""Application settings, loaded from the environment (see `.env.example`)."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-to-a-long-random-string"
MIN_PROD_JWT_SECRET_LEN = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173"  # comma-separated
    max_upload_mb: int = 25
    public_verify: bool = True

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_expire_minutes: int = 120

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "proofchain"

    s3_endpoint_url: str = ""
    s3_bucket: str = "proofchain-docs"
    s3_region: str = "ap-south-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_presign_expiry_seconds: int = 300

    chain_rpc_url: str = "http://127.0.0.1:8545"
    chain_id: int = 31337
    registry_address: str = ""
    anchor_private_key: str = ""
    chain_confirmations: int = 1
    explorer_tx_url: str = ""

    nlp_enabled: bool = True
    nlp_spacy_model: str = "en_core_web_sm"
    nlp_embeddings_enabled: bool = True
    nlp_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    nlp_llm_explanations: bool = False
    anthropic_api_key: str = ""
    nlp_llm_model: str = ""

    @model_validator(mode="after")
    def _reject_insecure_prod(self) -> "Settings":
        # anchor_private_key is checked in P4-03, not here (see TASKS.md).
        if self.app_env == "prod" and (
            self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < MIN_PROD_JWT_SECRET_LEN
        ):
            raise ValueError(
                f"JWT_SECRET must be a random value of >= {MIN_PROD_JWT_SECRET_LEN} chars in prod"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
