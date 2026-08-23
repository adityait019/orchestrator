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
# ✅ DEV-ONLY bypass toggle
# --------------------------------------------------
DEV_AUTH_ENABLED = os.getenv("DEV_AUTH_ENABLED", "false").lower() == "true"

if DEV_AUTH_ENABLED:
    logger.warning(
        "⚠️ DEV_AUTH_ENABLED=true — auth/me and the BFF trust boundary "
        "are BYPASSED for any request carrying X-Dev-User-Id. "
        "This must NEVER be set in a deployed environment."
    )


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

        return {
            "user_id": data.get("user_id") or data.get("id"),
            "tenant_id": data.get("tenant_id") or data.get("tenant"),
            "roles": data.get("roles", []),
            "raw": data,
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
    x_dev_user_id:       str | None = Header(default=None, alias="X-Dev-User-Id"),
    x_dev_tenant_id:     str | None = Header(default=None, alias="X-Dev-Tenant-Id"),
    x_dev_roles:         str | None = Header(default=None, alias="X-Dev-Roles"),
) -> dict:
    # ── DEV-ONLY: bypass everything when explicitly enabled ─────────────
    # Only takes effect if DEV_AUTH_ENABLED=true AND the caller actually
    # sends X-Dev-User-Id. No token, no BFF, no auth/me round trip needed —
    # you supply identity directly, same pattern as the WS auth frame.
    if DEV_AUTH_ENABLED and x_dev_user_id:
        return {
            "user_id":   x_dev_user_id,
            "tenant_id": x_dev_tenant_id or "dev-tenant",
            "roles":     [r.strip() for r in (x_dev_roles or "user").split(",") if r.strip()],
            "raw":       {"source": "dev-header-bypass"},
        }

    # ── Trust the BFF middleware's forwarded identity ────────────────────────
    if (x_middleware or "").lower() == "bff" \
            and x_forwarded_user and x_forwarded_tenant:
        return {
            "user_id":   x_forwarded_user,
            "tenant_id": x_forwarded_tenant,
            "roles":     [],
            "raw":       {"source": "bff-forwarded"},
        }

    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = creds.credentials
    user = await verify_token_via_auth_me(token)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not user.get("user_id") or not user.get("tenant_id"):
        logger.error("Auth response missing required fields: %s", user)
        raise HTTPException(status_code=401, detail="Invalid auth payload")

    return user


# --------------------------------------------------
# ✅ Admin Token Verification
# --------------------------------------------------
async def verify_admin_token(
    x_admin_token: str = Header(...),
):
    MASTER_TOKEN = os.getenv("SECRET_KEY", "super-secret")

    if x_admin_token != MASTER_TOKEN:
        raise HTTPException(status_code=403, detail="Unauthorized")