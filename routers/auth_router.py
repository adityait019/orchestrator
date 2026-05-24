import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from auth.deps import get_current_user
from pydantic import BaseModel
from session.session_manager import SessionManager
from auth.auth_schemas import LoginRequest, LoginResponse
import json
router = APIRouter(prefix="/auth", tags=["Auth"])

USER_DB_FILE = r"C:\Users\adity\project\orchestrator\auth\user_data.json"


@router.post("/signup")
async def signup(request: Request, login_req: LoginRequest):
    session_manager: SessionManager = request.app.state.session_manager

    await session_manager.ensure_session(
        user_id=login_req.user_id,
        session_id=login_req.session_id,
    )

    if not (login_req.user_id and login_req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Load tenants
    try:
        with open(USER_DB_FILE, "r") as f:
            tenants = json.load(f)
    except FileNotFoundError:
        tenants = []

    # Find tenant by tenant_id
    tenant = next((t for t in tenants if t["tenant_id"] == login_req.tenant_id), None)

    if tenant is None:
        tenant = {"tenant_id": login_req.tenant_id, "users": []}
        tenants.append(tenant)

    # Check if user already exists
    if any(user["user_id"] == login_req.user_id for user in tenant["users"]):
        raise HTTPException(status_code=400, detail="User already exists")

    # Add new user
    tenant["users"].append({
        "user_id": login_req.user_id,
        "password": login_req.password,
        "role": login_req.role,
    })

    with open(USER_DB_FILE, "w") as f:
        json.dump(tenants, f, indent=4)

    return LoginResponse(
        user_id=login_req.user_id,
        tenant_id=login_req.tenant_id,
        role=login_req.role,
    )



@router.get("/tenants")
async def list_tenants():
    try:
        with open(USER_DB_FILE, "r") as f:
            tenants = json.load(f)
    except FileNotFoundError:
        tenants = []
    return tenants


@router.get("/tenants/{tenant_id}/users")
async def list_users_for_tenant(tenant_id: str):
    try:
        with open(USER_DB_FILE, "r") as f:
            tenants = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No tenants found")

    tenant = next((t for t in tenants if t["tenant_id"] == tenant_id), None)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return tenant["users"]


@router.post("/login")
async def login(login_req: LoginRequest):
    # Load tenants
    try:
        with open(USER_DB_FILE, "r") as f:
            tenants = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No tenants found")

    # Search for user in all tenants
    for tenant in tenants:
        for user in tenant["users"]:
            if user["user_id"] == login_req.user_id and user["password"] == login_req.password:
                # ✅ Successful login
                return LoginResponse(
                    user_id=user["user_id"],
                    tenant_id=tenant["tenant_id"],
                    role=user["role"],
                )

    # ❌ Invalid credentials
    raise HTTPException(status_code=401, detail="Invalid credentials")
