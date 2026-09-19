"""OAuth (Google / GitHub) authentication and JWT session issuance.

Login uses the OAuth2 authorization-code flow. After a successful callback we
upsert a local user record and mint our own signed JWT, which the SPA stores
and sends as a Bearer token on subsequent requests.

Providers are only enabled when their client id/secret are configured, so the
app runs fine (auth simply unavailable) without any OAuth credentials.
"""
import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config
from ..db import get_db
from ..deps import require_user
from ..models import UserORM
from ..scraped import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

try:
    from authlib.integrations.starlette_client import OAuth

    _AUTHLIB_AVAILABLE = True
except ImportError:  # pragma: no cover - authlib is a declared dependency
    OAuth = None
    _AUTHLIB_AVAILABLE = False
    logger.warning("Authlib not installed; OAuth login disabled.")


def _build_oauth():
    if not _AUTHLIB_AVAILABLE:
        return None, {}
    oauth = OAuth()
    enabled = {}
    if config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET:
        oauth.register(
            name="google",
            client_id=config.GOOGLE_CLIENT_ID,
            client_secret=config.GOOGLE_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        enabled["google"] = "Google"
    if config.GITHUB_CLIENT_ID and config.GITHUB_CLIENT_SECRET:
        oauth.register(
            name="github",
            client_id=config.GITHUB_CLIENT_ID,
            client_secret=config.GITHUB_CLIENT_SECRET,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )
        enabled["github"] = "GitHub"
    return oauth, enabled


oauth, ENABLED_PROVIDERS = _build_oauth()


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


async def _upsert_user(db: AsyncSession, provider: str, provider_id, email, name, avatar_url) -> UserORM:
    user = (
        await db.execute(
            select(UserORM).where(
                UserORM.provider == provider, UserORM.provider_id == str(provider_id)
            )
        )
    ).scalars().first()
    if user is None:
        user = UserORM(provider=provider, provider_id=str(provider_id))
        db.add(user)
    user.email = email
    user.name = name
    user.avatar_url = avatar_url
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/providers")
async def list_providers():
    """Return the OAuth providers that are configured and available."""
    return [{"id": pid, "label": label} for pid, label in ENABLED_PROVIDERS.items()]


@router.get("/me", response_model=User)
async def me(user: UserORM = Depends(require_user)):
    return User.model_validate(user)


@router.get("/{provider}/login")
async def login(provider: str, request: Request):
    if provider not in ENABLED_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not configured")
    redirect_uri = f"{config.BACKEND_URL}/api/v1/auth/{provider}/callback"
    client = oauth.create_client(provider)
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/{provider}/callback")
async def callback(provider: str, request: Request, db: AsyncSession = Depends(get_db)):
    if provider not in ENABLED_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not configured")
    client = oauth.create_client(provider)
    try:
        token = await client.authorize_access_token(request)
    except Exception as exc:  # pragma: no cover - network / provider errors
        logger.warning("OAuth callback failed for %s: %s", provider, exc)
        return RedirectResponse(f"{config.FRONTEND_URL}/?auth_error=1")

    if provider == "google":
        info = token.get("userinfo") or await client.userinfo(token=token)
        user = await _upsert_user(
            db,
            provider="google",
            provider_id=info.get("sub"),
            email=info.get("email"),
            name=info.get("name"),
            avatar_url=info.get("picture"),
        )
    else:  # github
        resp = await client.get("user", token=token)
        profile = resp.json()
        email = profile.get("email")
        if not email:
            try:
                emails = (await client.get("user/emails", token=token)).json()
                primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
                email = (primary or (emails[0] if emails else {})).get("email")
            except Exception:  # pragma: no cover
                email = None
        user = await _upsert_user(
            db,
            provider="github",
            provider_id=profile.get("id"),
            email=email,
            name=profile.get("name") or profile.get("login"),
            avatar_url=profile.get("avatar_url"),
        )

    access_token = create_access_token(user.id)
    return RedirectResponse(f"{config.FRONTEND_URL}/?token={access_token}")
