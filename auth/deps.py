# auth/deps.py
import logging
import json
from fastapi import Depends, HTTPException, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

security = HTTPBearer()

USER_DB_FILE = r"C:\Users\adity\project\orchestrator\auth\user_data.json"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Dependency to validate user_id and password against dummy JSON database.
    Instead of a token, the client should send 'user_id:password' as the token.
    """
    token = credentials.credentials

    try:
        user_id, password = token.split(":")
    except ValueError:
        logger.warning("Invalid token format. Expected 'user_id:password'")
        raise HTTPException(status_code=401, detail="Invalid token format")

    # Load tenants and users
    try:
        with open(USER_DB_FILE, "r") as f:
            tenants = json.load(f)
    except FileNotFoundError:
        logger.error("User database file not found")
        raise HTTPException(status_code=500, detail="User database not found")

    # Search for user in all tenants
    for tenant in tenants:
        for user in tenant["users"]:
            if user["user_id"] == user_id and user["password"] == password:
                logger.info(f"Authenticated user {user_id} in tenant {tenant['tenant_id']}")
                return {
                    "user_id": user_id,
                    "tenant_id": tenant["tenant_id"],
                    "role": user["role"],
                }

    logger.warning(f"Authentication failed for user {user_id}")
    raise HTTPException(status_code=401, detail="Invalid credentials")
