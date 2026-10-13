"""Fast safe operator error and explicit serving role contracts; no deployment."""
import importlib.util
import json

import pytest

from app.config import ROOT, Settings


def test_acceptance_cli_withholds_unconfigured_permission_without_private_output(monkeypatch, capsys):
    from app import config
    settings = Settings(_env_file=None, demo_mode=True, encryption_key="")
    monkeypatch.setattr(config, "load_settings", lambda: settings)
    spec = importlib.util.spec_from_file_location("final_publication_cli_test", ROOT / "scripts/review_final_publication.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["--candidate", "/absent-private-candidate", "--authorization", "/absent-private-signature"]) == 2
    result = capsys.readouterr()
    assert json.loads(result.err) == {"error": "whole_release_approval_failed", "publication_performed": False}
    assert result.out == "" and "absent-private" not in result.err


def test_public_review_role_selection_is_explicit_and_fail_closed():
    settings = Settings(_env_file=None, graph_trusted_review_key="/trusted/component-public.pem",
                        graph_final_review_trusted_key="/trusted/final-public.pem")
    assert str(settings.serving_review_key) == "/trusted/component-public.pem"
    settings.graph_serving_review_role = "final"
    assert str(settings.serving_review_key) == "/trusted/final-public.pem"
    settings.graph_final_review_trusted_key = ""
    assert settings.serving_review_key is None
    with pytest.raises(ValueError):
        Settings(_env_file=None, graph_serving_review_role="automatic")
