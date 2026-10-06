import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_", env_file=str(ROOT / ".env"), extra="ignore")
    demo_mode: bool = False
    database_url: str = "sqlite:///./.data/workspace.db"
    data_dir: Path = ROOT / ".data"
    encryption_key: str = Field(default="", repr=False)
    bootstrap_username: str = ""
    bootstrap_password: str = Field(default="", repr=False)
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8000"
    cookie_secure: bool = True
    graph_url: str = ""
    graph_user: str = ""
    graph_password: str = Field(default="", repr=False)
    graph_release_dir: str = ""
    graph_trusted_review_key: str = ""
    public_source_dir: Path = ROOT / ".public-sources"
    opensearch_url: str = ""
    search_release_id: str = ""
    search_index: str = "law-public-passages"
    gateway_url: str = ""
    gateway_token: str = Field(default="", repr=False)
    gateway_enabled: bool = False
    gateway_allowlist: str = "www.mevzuat.gov.tr,mevzuat.gov.tr,www.resmigazete.gov.tr,resmigazete.gov.tr"
    upload_max_bytes: int = 20 * 1024 * 1024
    clamav_host: str = ""
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    scanner_timeout_seconds: int = Field(default=30, ge=1, le=120)
    scanner_max_signature_age_days: int = Field(default=7, ge=1, le=14)
    extraction_url: str = ""
    extraction_token: str = Field(default="", repr=False)
    extraction_timeout_seconds: int = 60
    research_budget_seconds: int = Field(default=300, ge=10, le=1800)
    session_hours: int = 8
    provider_base_url: str = Field(default="", validation_alias="LLM_PROVIDER_BASE_URL")
    provider_api_key: str = Field(default="", validation_alias="LLM_PROVIDER_API_KEY", repr=False)
    provider_tenant_id: str = Field(default="lawyer-assistant-v1", validation_alias="LLM_PROVIDER_TENANT_ID")
    provider_org_id: str = Field(default="org-lawyer", validation_alias="LLM_PROVIDER_ORG_ID")
    provider_key_id: str = Field(
        default="lawyer-assistant-v1-primary", validation_alias="LLM_PROVIDER_KEY_ID"
    )
    provider_model: str = Field(default="", validation_alias="LLM_PROVIDER_MODEL")
    provider_context_limit: int = Field(default=8192, validation_alias="LLM_PROVIDER_CONTEXT_LIMIT")
    provider_identity_verified: bool = Field(default=False, validation_alias="LLM_PROVIDER_IDENTITY_VERIFIED")
    provider_allow_plain_http: bool = Field(default=False, validation_alias="LLM_PROVIDER_ALLOW_PLAIN_HTTP")
    provider_tunnel_url: str = Field(default="", validation_alias="LLM_PROVIDER_TUNNEL_URL")
    provider_tunnel_approved: bool = Field(default=False, validation_alias="LLM_PROVIDER_TUNNEL_APPROVED")
    provider_tunnel_approved_host: str = Field(default="", validation_alias="LLM_PROVIDER_TUNNEL_APPROVED_HOST")
    # A local URL and pinned model do not stop an engine from cloud fallback.
    # This is a deployment attestation, separate from credential authentication.
    provider_cloud_fallback_disabled: bool = Field(
        default=False, validation_alias="LLM_PROVIDER_CLOUD_FALLBACK_DISABLED"
    )

    @property
    def origins(self):
        return [s.strip() for s in self.allowed_origins.split(",") if s.strip()]


def load_settings():
    # A synthetic demonstration must never load credentials from the user's root .env.
    if os.environ.get("LA_DEMO_MODE", "").lower() in {"1", "true", "yes"}:
        return Settings(_env_file=None)
    return Settings()
