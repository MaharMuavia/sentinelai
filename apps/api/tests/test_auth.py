import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app import auth
from app.config import settings


def test_static_auth_uses_constant_time_bearer_check(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "static")
    monkeypatch.setattr(settings, "SENTINEL_AUTH_TOKEN", "correct-token")

    principal = auth.require_mutation_authorization("Bearer correct-token")

    assert principal.subject == "static-token-operator"
    with pytest.raises(HTTPException) as exc_info:
        auth.require_mutation_authorization("Bearer wrong-token")
    assert exc_info.value.status_code == 401


def test_static_auth_fails_closed_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "static")
    monkeypatch.setattr(settings, "SENTINEL_AUTH_TOKEN", None)

    with pytest.raises(HTTPException) as exc_info:
        auth.require_mutation_authorization(None)

    assert exc_info.value.status_code == 503


def test_oidc_auth_validates_claims_and_scope(monkeypatch):
    now = int(time.time())
    claims = {
        "sub": "operator@example.com",
        "iss": "https://identity.example.com/",
        "aud": "sentinel-api",
        "iat": now,
        "exp": now + 300,
        "scope": "openid sentinel:mutate",
    }
    monkeypatch.setattr(settings, "AUTH_MODE", "oidc")
    monkeypatch.setattr(settings, "OIDC_ISSUER", claims["iss"])
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", claims["aud"])
    monkeypatch.setattr(settings, "OIDC_JWKS_URL", "https://identity.example.com/.well-known/jwks.json")
    monkeypatch.setattr(settings, "OIDC_REQUIRED_SCOPES", "sentinel:mutate")
    monkeypatch.setattr(settings, "OIDC_ALGORITHM", "RS256")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encoded_token = jwt.encode(claims, private_key, algorithm="RS256")

    class SigningKey:
        key = private_key.public_key()

    class JwkClient:
        def get_signing_key_from_jwt(self, token):
            assert token == encoded_token
            return SigningKey()

    monkeypatch.setattr(auth, "_jwk_client", lambda url: JwkClient())

    principal = auth.require_mutation_authorization(f"Bearer {encoded_token}")

    assert principal.subject == claims["sub"]
    assert principal.auth_mode == "oidc"
    assert "sentinel:mutate" in principal.scopes


def test_oidc_auth_rejects_missing_scope(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "oidc")
    monkeypatch.setattr(settings, "OIDC_ISSUER", "https://identity.example.com/")
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", "sentinel-api")
    monkeypatch.setattr(settings, "OIDC_JWKS_URL", "https://identity.example.com/jwks.json")
    monkeypatch.setattr(settings, "OIDC_REQUIRED_SCOPES", "sentinel:mutate")
    claims = {
        "sub": "read-only@example.com",
        "iss": settings.OIDC_ISSUER,
        "aud": settings.OIDC_AUDIENCE,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "scope": "openid profile",
    }
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encoded_token = jwt.encode(claims, private_key, algorithm="RS256")

    class SigningKey:
        key = private_key.public_key()

    class JwkClient:
        def get_signing_key_from_jwt(self, token):
            assert token == encoded_token
            return SigningKey()

    monkeypatch.setattr(auth, "_jwk_client", lambda url: JwkClient())

    with pytest.raises(HTTPException) as exc_info:
        auth.require_mutation_authorization(f"Bearer {encoded_token}")

    assert exc_info.value.status_code == 403
