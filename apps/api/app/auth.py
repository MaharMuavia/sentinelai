"""Authentication boundary for endpoints that can create external side effects."""

from __future__ import annotations

import hmac
from functools import lru_cache
from typing import Any, Optional

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient
from pydantic import BaseModel

from app.config import settings


class MutationPrincipal(BaseModel):
    subject: str
    auth_mode: str
    scopes: list[str]


def _extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Bearer authorization is required")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid bearer authorization")
    return token.strip()


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def _claim_scopes(claims: dict[str, Any]) -> set[str]:
    scopes: set[str] = set()
    scope = claims.get("scope")
    if isinstance(scope, str):
        scopes.update(scope.split())
    scp = claims.get("scp")
    if isinstance(scp, str):
        scopes.update(scp.split())
    elif isinstance(scp, list):
        scopes.update(str(value) for value in scp)
    return scopes


def _validate_oidc_token(token: str) -> MutationPrincipal:
    if not settings.OIDC_ISSUER or not settings.OIDC_AUDIENCE or not settings.OIDC_JWKS_URL:
        raise HTTPException(status_code=503, detail="OIDC mutation authorization is not fully configured")

    try:
        signing_key = _jwk_client(settings.OIDC_JWKS_URL).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=[settings.OIDC_ALGORITHM],
            audience=settings.OIDC_AUDIENCE,
            issuer=settings.OIDC_ISSUER,
            leeway=settings.OIDC_CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="OIDC token validation failed") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="OIDC signing keys are unavailable") from exc

    scopes = _claim_scopes(claims)
    required_scopes = {value for value in settings.OIDC_REQUIRED_SCOPES.split() if value}
    missing_scopes = sorted(required_scopes - scopes)
    if missing_scopes:
        raise HTTPException(status_code=403, detail=f"Missing required scope(s): {', '.join(missing_scopes)}")

    return MutationPrincipal(subject=str(claims["sub"]), auth_mode="oidc", scopes=sorted(scopes))


def require_mutation_authorization(
    authorization: Optional[str] = Header(None),
) -> MutationPrincipal:
    """Authenticate an external-action request using the configured mode."""
    auth_mode = settings.AUTH_MODE.strip().lower()

    if auth_mode == "oidc":
        if not settings.OIDC_ISSUER or not settings.OIDC_AUDIENCE or not settings.OIDC_JWKS_URL:
            raise HTTPException(status_code=503, detail="OIDC mutation authorization is not fully configured")
        token = _extract_bearer_token(authorization)
        return _validate_oidc_token(token)
    if auth_mode != "static":
        raise HTTPException(status_code=503, detail="Unsupported mutation authorization mode")

    expected_token = settings.SENTINEL_AUTH_TOKEN
    if not expected_token:
        raise HTTPException(status_code=503, detail="Mutation authorization is not configured")
    token = _extract_bearer_token(authorization)
    if not hmac.compare_digest(token, expected_token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return MutationPrincipal(subject="static-token-operator", auth_mode="static", scopes=["sentinel:mutate"])
