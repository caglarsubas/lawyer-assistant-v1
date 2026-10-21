"""Synthetic mounted secrets, fixed diagnostics and environment non-disclosure."""

import json
import os
import runpy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.extraction_worker import create_app
from app.runtime_secrets import RuntimeSecretError, read_secret_file

ROOT = Path(__file__).resolve().parents[2]
VALUE = "SYNTHETIC-secret-never-emit-12345678901234567890"


def secret(tmp_path, name="token", value=VALUE):
    path = tmp_path / name
    path.write_text(value + "\n")
    path.chmod(0o600)
    return path


def test_settings_file_secrets_never_export_to_repr_dump_or_environment(tmp_path, monkeypatch):
    path = secret(tmp_path)
    monkeypatch.delenv("LA_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("LA_ENCRYPTION_KEY_FILE", str(path))
    settings = Settings(_env_file=None)
    assert settings.encryption_key == VALUE
    assert VALUE not in repr(settings) + settings.model_dump_json() + json.dumps(dict(os.environ))
    assert "encryption_key" not in settings.model_dump()
    assert Settings.model_validate(settings).encryption_key == VALUE


def test_database_and_provider_secrets_are_loaded_without_serializing_values(tmp_path):
    db = secret(tmp_path, "database", "postgresql://user:fake-password@host/database")
    provider = secret(tmp_path, "provider")
    settings = Settings(_env_file=None, database_url_file=str(db), LLM_PROVIDER_API_KEY_FILE=str(provider))
    assert settings.database_url == db.read_text().strip() and settings.provider_api_key == VALUE
    assert "fake-password" not in repr(settings) + settings.model_dump_json()
    assert VALUE not in repr(settings) + settings.model_dump_json()


def test_file_conflict_never_creates_a_pydantic_input_value_dump(tmp_path):
    path = secret(tmp_path)
    with pytest.raises(RuntimeSecretError) as caught:
        Settings(_env_file=None, encryption_key=VALUE, encryption_key_file=str(path))
    assert VALUE not in str(caught.value) and str(path) not in str(caught.value)


@pytest.mark.parametrize("value", ["a\nb", "a\x00b", "a\rb", "", "x" * 16385])
def test_invalid_file_values_fail_without_echoing_input(tmp_path, value):
    path = secret(tmp_path, value=value)
    with pytest.raises(RuntimeSecretError) as caught:
        read_secret_file(path)
    assert str(path) not in str(caught.value)


def test_missing_symlink_fifo_and_writable_files_fail_closed(tmp_path):
    original = secret(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(original)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, 0o600)
    writable = secret(tmp_path, "writable")
    writable.chmod(0o666)
    for path in [tmp_path / "missing", link, fifo, writable, tmp_path]:
        with pytest.raises(RuntimeSecretError):
            read_secret_file(path)


def test_empty_provider_file_means_unconfigured_not_fallback(tmp_path):
    path = secret(tmp_path, value="")
    settings = Settings(_env_file=None, LLM_PROVIDER_API_KEY_FILE=str(path))
    assert not settings.provider_api_key and not settings.provider_base_url


def test_isolated_worker_uses_only_its_mounted_token(tmp_path, monkeypatch):
    path = secret(tmp_path)
    monkeypatch.delenv("LA_EXTRACTION_TOKEN", raising=False)
    monkeypatch.setenv("LA_EXTRACTION_TOKEN_FILE", str(path))
    with TestClient(create_app()) as client:
        assert client.get("/ready", headers={"Authorization": "Bearer retired-synthetic-token"}).status_code == 401
        assert client.get("/ready", headers={"Authorization": "Bearer " + VALUE}).status_code == 200
    assert "LA_EXTRACTION_TOKEN" not in os.environ


def test_diagnostic_projection_ignores_nested_values_and_unknown_health(tmp_path):
    project = runpy.run_path(str(ROOT / "scripts/runtime_diagnostics.py"))
    container = {"Config": {"Labels": {"com.docker.compose.service": "api", "private": VALUE},
                            "Env": ["LA_ENCRYPTION_KEY=" + VALUE, "LA_DATABASE_URL=" + VALUE]},
                 "State": {"Running": True, "Health": {"Status": VALUE}},
                 "HostConfig": {"ReadonlyRootfs": True, "private": VALUE}}
    result = project["safe_projection"]([container])
    assert VALUE not in json.dumps(result) and result["services"][0]["health"] == "unknown"
    assert result["services"][0]["literal_secret_environment_present"]
    container["Config"]["Env"] = ["LA_ENCRYPTION_KEY_FILE=/run/secrets/encryption_key"]
    assert not project["safe_projection"]([container])["services"][0]["literal_secret_environment_present"]
    container["Config"]["Labels"]["com.docker.compose.service"] = VALUE
    with pytest.raises(ValueError):
        project["safe_projection"]([container])
