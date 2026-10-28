import json
import os
import stat

import pytest
from fastapi.testclient import TestClient

from seabirds.app import create_app
from seabirds.config import Settings
from seabirds.github import GitHubPublisher

URL = "/api/generator/github/settings"
SECRET = "synthetic-private-credential-not-a-real-github-token"
AUTHOR = {"name": "Lucas QA", "email": "qa@example.invalid"}


def test_secret_encrypted_persisted_not_returned_and_blank_keeps_it(tmp_path, monkeypatch):
    monkeypatch.delenv("SEABIRDS_GITHUB_TOKEN", raising=False)
    with TestClient(create_app(Settings(tmp_path))) as client:
        saved = client.post(URL, json={**AUTHOR, "token_action": "replace", "token": SECRET})
        assert saved.status_code == 200 and saved.json()["token_source"] == "web"
        assert SECRET not in saved.text and "encrypted_token" not in saved.text
        stored = (tmp_path / "secrets/github.json").read_text()
        assert SECRET not in stored and "encrypted_token" in stored
        assert SECRET not in (tmp_path / "secrets/github.key").read_text()
        result = client.post(URL, json={**AUTHOR, "token": "", "token_action": "keep"})
        assert result.status_code == 200 and result.json()["token_configured"]
        assert SECRET not in client.get(URL).text
    restarted = GitHubPublisher(tmp_path)
    assert restarted.token == SECRET
    assert restarted.environment()["SEABIRDS_GITHUB_TOKEN"] == SECRET
    if os.name != "nt":
        assert stat.S_IMODE((tmp_path / "secrets").stat().st_mode) == 0o700
        assert stat.S_IMODE((tmp_path / "secrets/github.json").stat().st_mode) == 0o600
        assert stat.S_IMODE((tmp_path / "secrets/github.key").stat().st_mode) == 0o600


def test_rotation_and_removal_override_environment_without_reactivation(tmp_path, monkeypatch):
    monkeypatch.setenv("SEABIRDS_GITHUB_TOKEN", "environment-only-token")
    with TestClient(create_app(Settings(tmp_path))) as client:
        assert client.get(URL).json()["token_source"] == "environment"
        assert (
            client.post(
                URL, json={**AUTHOR, "token_action": "replace", "token": SECRET}
            ).status_code
            == 200
        )
        assert (
            client.post(
                URL,
                json={**AUTHOR, "token_action": "replace", "token": "replacement-synthetic-token"},
            ).status_code
            == 200
        )
        assert GitHubPublisher(tmp_path).token == "replacement-synthetic-token"
        removed = client.post(URL, json={**AUTHOR, "token_action": "remove"})
        assert removed.status_code == 200 and not removed.json()["token_configured"]
    restarted = GitHubPublisher(tmp_path)
    assert restarted.token == ""
    assert "SEABIRDS_GITHUB_TOKEN" not in restarted.environment()
    assert "encrypted_token" not in (tmp_path / "secrets/github.json").read_text()


@pytest.mark.parametrize(
    "token", [SECRET + "\n", {"private": SECRET}, [SECRET], "COLE_O_TOKEN_REAL_AQUI", "x" * 4097]
)
def test_validation_errors_never_echo_secret(tmp_path, token):
    with TestClient(create_app(Settings(tmp_path))) as client:
        response = client.post(URL, json={**AUTHOR, "token_action": "replace", "token": token})
        assert response.status_code == 422
        assert SECRET not in response.text and "x" * 100 not in response.text
        assert not (tmp_path / "secrets/github.json").exists()


def test_settings_require_authentication_and_same_origin(tmp_path):
    with TestClient(create_app(Settings(tmp_path, password="qa-password"))) as client:
        assert client.get(URL).status_code == 401
        assert (
            client.post(
                URL, json={**AUTHOR, "token_action": "replace", "token": SECRET}
            ).status_code
            == 401
        )
        response = client.post(
            URL,
            json={**AUTHOR, "token_action": "replace", "token": SECRET},
            auth=("admin", "qa-password"),
            headers={"Origin": "http://other.example"},
        )
        assert response.status_code == 403 and not (tmp_path / "secrets/github.json").exists()
        assert SECRET not in response.text


def test_missing_encryption_key_is_recoverable_from_web(tmp_path):
    with TestClient(create_app(Settings(tmp_path))) as client:
        client.post(
            URL, json={**AUTHOR, "token_action": "replace", "token": SECRET}
        ).raise_for_status()
    (tmp_path / "secrets/github.key").unlink()
    with TestClient(create_app(Settings(tmp_path))) as client:
        status = client.get(URL).json()
        assert status["token_error"] and not status["token_configured"]
        assert (
            client.post(
                URL, json={**AUTHOR, "token_action": "replace", "token": SECRET}
            ).status_code
            == 200
        )
    assert GitHubPublisher(tmp_path).token == SECRET


def test_invalid_identity_does_not_replace_existing_secret(tmp_path):
    service = GitHubPublisher(tmp_path)
    service.configure(**AUTHOR, action="replace", token=SECRET)
    before = json.loads((tmp_path / "secrets/github.json").read_text())
    with pytest.raises(ValueError):
        service.configure("bad\nname", "invalid-email", action="replace", token="other-token")
    assert json.loads((tmp_path / "secrets/github.json").read_text()) == before
