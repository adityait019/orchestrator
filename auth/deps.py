# auth/deps.py

import logging
import httpx
from fastapi import Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

logger = logging.getLogger(__name__)

AUTH_ME_URL = os.getenv("AUTH_ME_URL", "http://localhost:8000/auth/me")
bearer = HTTPBearer(auto_error=False)


# --------------------------------------------------
# ✅ Verify token via external auth service
# --------------------------------------------------
async def verify_token_via_auth_me(token: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(
                AUTH_ME_URL,
                headers={"Authorization": f"Bearer {token}"},
            )

        if res.status_code != 200:
            logger.warning(
                "Auth failed: status=%s body=%s",
                res.status_code,
                res.text,
            )
            return None

        try:
            data = res.json()
        except Exception:
            logger.error("Auth service returned invalid JSON")
            return None

        # ✅ Normalize response (CRITICAL for consistency)
        return {
            "user_id": data.get("user_id") or data.get("id"),
            "tenant_id": data.get("tenant_id") or data.get("tenant"),
            "roles": data.get("roles", []),
            "raw": data,  # keep original if needed
        }

    except httpx.TimeoutException:
        logger.error("Auth service timeout")
        return None
    except httpx.RequestError as e:
        logger.error("Auth service request error: %s", str(e))
        return None


# --------------------------------------------------
# ✅ Dependency for authenticated user
# --------------------------------------------------
async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    x_middleware:        str | None = Header(default=None),
    x_forwarded_user:    str | None = Header(default=None),
    x_forwarded_tenant:  str | None = Header(default=None),
) -> dict:
    # ── Trust the BFF middleware's forwarded identity ────────────────────────
    # If the request carries X-Middleware: bff along with the forwarded user
    # and tenant headers, trust them. The middleware already validated the
    # HttpOnly session cookie before proxying, so this is the canonical BFF
    # trust boundary — there's no need for the orchestrator to round-trip back
    # to the tenant /auth/me (which is often unreachable on laptop dev setups
    # because AUTH_ME_URL defaults to a fixed remote IP).
    #
    # In production, restrict the orchestrator to listen only on internal
    # networks so external callers can't forge these headers. The middleware
    # is the only thing that should ever speak directly to the orchestrator.
    if (x_middleware or "").lower() == "bff" \
            and x_forwarded_user and x_forwarded_tenant:
        return {
            "user_id":   x_forwarded_user,
            "tenant_id": x_forwarded_tenant,
            "roles":     [],
            "raw":       {"source": "bff-forwarded"},
        }

    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
        )

    token = creds.credentials

    user = await verify_token_via_auth_me(token)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    # ✅ Validate required fields (align with WebSocket handler)
    if not user.get("user_id") or not user.get("tenant_id"):
        logger.error("Auth response missing required fields: %s", user)
        raise HTTPException(
            status_code=401,
            detail="Invalid auth payload",
        )

    return user


# --------------------------------------------------
# ✅ Admin Token Verification
# --------------------------------------------------
async def verify_admin_token(
    x_admin_token: str = Header(...),
):
    MASTER_TOKEN = os.getenv("SECRET_KEY", "super-secret")

    if x_admin_token != MASTER_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized",
        )