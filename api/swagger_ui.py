"""
Orchestrator — password-protected Swagger UI.

Config (env vars, add to .env):
    SWAGGER_PASSWORD=docs-changeme    # empty = disabled
    SWAGGER_ACCESS=lan                # "lan" | "localhost"
    SWAGGER_TOKEN_TTL=1800            # seconds (30 min)

Endpoints (all include_in_schema=False):
    GET  /docs/login  → login page
    POST /docs/login  → authenticate, set cookie
    GET  /docs/logout → clear cookie
    GET  /docs        → Swagger UI (protected)
    GET  /redoc       → ReDoc (protected)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import HTMLResponse, RedirectResponse

from api.ip_utils import check_access, get_client_ip

router = APIRouter(tags=["swagger-auth"])

COOKIE = "__orch_docs"


def _cfg():
    return {
        "password": os.getenv("SWAGGER_PASSWORD", "docs-changeme"),
        "access":   os.getenv("SWAGGER_ACCESS", "lan"),
        "ttl":      int(os.getenv("SWAGGER_TOKEN_TTL", "1800")),
    }


def _sign(pw: str, ts: int) -> str:
    return hmac.new(pw.encode(), f"orch_docs:{ts}".encode(), hashlib.sha256).hexdigest()[:32]


def _make_token(pw: str) -> str:
    ts = int(time.time())
    return f"{ts}.{_sign(pw, ts)}"


def _verify(token: str, pw: str, ttl: int) -> bool:
    try:
        ts_str, sig = token.split(".", 1)
        ts = int(ts_str)
        if time.time() - ts > ttl:
            return False
        return hmac.compare_digest(sig, _sign(pw, ts))
    except Exception:
        return False


# ── Login page ─────────────────────────────────────────────────────────────────

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#07071a;color:#e0e0e0;font-family:'Courier New',monospace;
  display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#0f0f1a;border:1px solid #1a1a3a;padding:48px 40px;width:400px;
  box-shadow:0 0 60px rgba(68,136,255,0.08)}
.logo{color:#4488ff;font-size:22px;font-weight:900;letter-spacing:2px;margin-bottom:6px}
.sub{color:#333;font-size:9px;letter-spacing:3px;margin-bottom:32px}
label{display:block;font-size:9px;color:#666;letter-spacing:2px;
  text-transform:uppercase;margin-bottom:6px;margin-top:18px}
input[type=password]{width:100%;background:#080816;border:1px solid #222;color:#e0e0e0;
  font-family:monospace;font-size:13px;padding:10px 14px;outline:none;transition:border-color .15s}
input[type=password]:focus{border-color:#4488ff}
button{width:100%;margin-top:24px;background:#4488ff;color:#fff;border:none;
  padding:12px;font-family:monospace;font-size:12px;font-weight:700;
  letter-spacing:2px;text-transform:uppercase;cursor:pointer;transition:opacity .15s}
button:hover{opacity:.85}
.err{color:#ff4444;font-size:11px;margin-top:12px;padding:8px 12px;
  background:#1a0000;border:1px solid rgba(255,68,68,0.25)}
.hint{color:#1e1e3a;font-size:10px;margin-top:20px;line-height:1.8}
"""

_LOGIN = """\
<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orchestrator API — Login</title>
<style>CSS</style></head><body>
<div class="card">
  <div class="logo">⚡ ORCHESTRATOR</div>
  <div class="sub">SWAGGER UI — PROTECTED</div>
  <form method="POST" action="/docs/login">
    <label>Password</label>
    <input type="password" name="password" autofocus autocomplete="current-password">
    ERR
    <button type="submit">ACCESS DOCS →</button>
  </form>
  <div class="hint">Session cookie · clears on browser close<br>
  Set SWAGGER_PASSWORD in orchestrator .env</div>
</div></body></html>"""


def _login_page(err: str = "") -> str:
    return _LOGIN.replace("CSS", _CSS).replace("ERR", err)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/docs/login", response_class=HTMLResponse, include_in_schema=False)
async def docs_login_page(request: Request):
    cfg = _cfg()
    ip = get_client_ip(request)
    check_access(ip, cfg["access"], "Swagger UI")
    if not cfg["password"]:
        from fastapi import HTTPException
        raise HTTPException(404, "Swagger UI disabled (set SWAGGER_PASSWORD)")
    return HTMLResponse(_login_page())


@router.post("/docs/login", include_in_schema=False)
async def docs_login_submit(request: Request, password: str = Form(...)):
    cfg = _cfg()
    ip = get_client_ip(request)
    check_access(ip, cfg["access"], "Swagger UI")
    if not cfg["password"]:
        from fastapi import HTTPException
        raise HTTPException(404, "Disabled")
    if not hmac.compare_digest(password.encode(), cfg["password"].encode()):
        return HTMLResponse(_login_page('<div class="err">❌ Incorrect password</div>'), 401)
    resp = RedirectResponse("/docs", status_code=303)
    resp.set_cookie(COOKIE, _make_token(cfg["password"]),
                    httponly=True, samesite="lax", secure=False, path="/")
    return resp


@router.get("/docs/logout", include_in_schema=False)
async def docs_logout():
    resp = RedirectResponse("/docs/login", status_code=303)
    resp.delete_cookie(COOKIE, path="/")
    return resp


@router.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def docs_ui(request: Request,
                  *,
                  __orch_docs: Optional[str] = Cookie(default=None)):
    cfg = _cfg()
    ip  = get_client_ip(request)
    check_access(ip, cfg["access"], "Swagger UI")
    if not cfg["password"]:
        from fastapi import HTTPException
        raise HTTPException(404, "Disabled")
    if not __orch_docs or not _verify(__orch_docs, cfg["password"], cfg["ttl"]):
        return RedirectResponse("/docs/login", status_code=302)

    ttl = cfg["ttl"]
    html = f"""\
<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orchestrator API — Swagger UI</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
<style>
*{{box-sizing:border-box}}body{{margin:0}}
.od-bar{{background:#07071a;color:#e0e0e0;padding:0 20px;height:40px;
  display:flex;align-items:center;gap:14px;font-family:'Courier New',monospace;
  font-size:11px;border-bottom:2px solid #4488ff;position:sticky;top:0;z-index:9999}}
.od-logo{{color:#4488ff;font-size:16px;font-weight:900}}
.od-title{{color:#e0e0e0;letter-spacing:2px;font-size:10px;font-weight:700}}
.od-badge{{font-size:8px;padding:2px 7px;border:1px solid rgba(68,136,255,.4);
  color:#4488ff;letter-spacing:1.5px;font-weight:700;border-radius:2px}}
.od-right{{margin-left:auto;display:flex;align-items:center;gap:12px}}
.od-ttl{{font-size:10px;color:#aabbcc;font-variant-numeric:tabular-nums}}
.od-sep{{width:1px;height:16px;background:#1e2a3a}}
.od-logout{{background:transparent;border:1px solid #2a3a4a;color:#8899bb;
  padding:4px 12px;cursor:pointer;font-family:'Courier New',monospace;
  font-size:9px;letter-spacing:1.5px;text-transform:uppercase;text-decoration:none;
  border-radius:2px;transition:all .15s}}
.od-logout:hover{{border-color:#ff4444;color:#ff6666}}
#swagger-ui .topbar{{display:none!important}}
</style></head><body>
<div class="od-bar">
  <span class="od-logo">⚡</span>
  <span class="od-title">ORCHESTRATOR API</span>
  <span class="od-badge">SWAGGER UI</span>
  <div class="od-right">
    <span class="od-ttl" id="od-ttl">Session active</span>
    <div class="od-sep"></div>
    <span style="font-size:9px;color:#7788aa">LAN only · protected</span>
    <div class="od-sep"></div>
    <a href="/docs/logout" class="od-logout">LOGOUT →</a>
  </div>
</div>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
const TTL={ttl};let r=TTL;const el=document.getElementById('od-ttl');
setInterval(()=>{{r--;if(r<=0){{el.textContent='Expired';el.style.color='#ff4444';return;}}
const m=Math.floor(r/60),s=r%60;el.textContent=`Session: ${{m}}m ${{s}}s`;}},1000);
SwaggerUIBundle({{url:'/openapi.json',dom_id:'#swagger-ui',
  presets:[SwaggerUIBundle.presets.apis],layout:'BaseLayout',
  persistAuthorization:true,displayRequestDuration:true,filter:true,tryItOutEnabled:false}});
</script></body></html>"""
    return HTMLResponse(html)


@router.get("/redoc", response_class=HTMLResponse, include_in_schema=False)
async def redoc_ui(request: Request,
                   *,
                   __orch_docs: Optional[str] = Cookie(default=None)):
    cfg = _cfg()
    ip  = get_client_ip(request)
    check_access(ip, cfg["access"], "ReDoc")
    if not cfg["password"]:
        from fastapi import HTTPException
        raise HTTPException(404, "Disabled")
    if not __orch_docs or not _verify(__orch_docs, cfg["password"], cfg["ttl"]):
        return RedirectResponse("/docs/login", status_code=302)
    return get_redoc_html(openapi_url="/openapi.json",
                          title="Orchestrator API — ReDoc")
