"""Request dependencies: caller identity, user resolution, and rate limiting.

`current_identity` keys everything (rate limiting, saved-search ownership) on a
stable string. When a valid Bearer JWT is present it resolves to ``user:<id>``
(so an authenticated user's saved searches follow them and can be emailed);
otherwise it falls back to ``ip:<addr>`` so anonymous callers are still scoped
and throttled.
"""

import jwt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from . import config
from .config import get_settings
from .db import get_db
from .models import UserORM
from .services.ratelimit import build_limiter

_settings = get_settings()
_limiter = build_limiter(_settings)


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def decode_user_id(token: str | None) -> int | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def current_identity(
    request: Request,
    authorization: str | None = Header(default=None),
) -> str:
    user_id = decode_user_id(_bearer_token(authorization))
    if user_id is not None:
        return f"user:{user_id}"
    client = request.client.host if request.client else "unknown"
    return f"ip:{client}"


async def get_optional_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> UserORM | None:
    user_id = decode_user_id(_bearer_token(authorization))
    if user_id is None:
        return None
    return await db.get(UserORM, user_id)


async def require_user(user: UserORM | None = Depends(get_optional_user)) -> UserORM:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def rate_limit(identity: str = Depends(current_identity)) -> str:
    allowed, retry_after = await _limiter.check(identity)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Slow down.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    return identity
