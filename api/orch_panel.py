"""
Orchestrator Admin Control Panel — /__ctrl__

Password-protected, LAN-only dashboard that shows:
  • Overview: session counts, agent stats, recent activity
  • Sessions: orchestration sessions with status and duration
  • Invocations: per-agent invocations with token usage
  • Agents: registered agents with health status
  • Artifacts: uploaded/generated files

Config (env vars):
    ORCH_PANEL_PASSWORD=panel-changeme   # empty = disabled
    ORCH_PANEL_ACCESS=lan                # "lan" | "localhost"
    ORCH_PANEL_TOKEN_TTL=3600            # seconds (1 hour)

Mount in main.py:
    from api.orch_panel import orch_panel_app
    app.mount("/__ctrl__", orch_panel_app)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import Cookie, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from api.ip_utils import check_access, get_client_ip

# ── Auth helpers ──────────────────────────────────────────────────────────────

COOKIE = "__orch_ctrl"


def _cfg():
    return {
        "password": os.getenv("ORCH_PANEL_PASSWORD", "panel-changeme"),
        "access":   os.getenv("ORCH_PANEL_ACCESS", "lan"),
        "ttl":      int(os.getenv("ORCH_PANEL_TOKEN_TTL", "3600")),
    }


def _sign(ts: int) -> str:
    pw = os.getenv("ORCH_PANEL_PASSWORD", "panel-changeme")
    return hmac.new(pw.encode(), f"orch_ctrl:{ts}".encode(), hashlib.sha256).hexdigest()[:32]


def _make_token() -> str:
    ts = int(time.time())
    return f"{ts}.{_sign(ts)}"


def _verify_token(token: str) -> bool:
    try:
        ts_str, sig = token.split(".", 1)
        ts  = int(ts_str)
        ttl = int(os.getenv("ORCH_PANEL_TOKEN_TTL", "3600"))
        if time.time() - ts > ttl:
            return False
        return hmac.compare_digest(sig, _sign(ts))
    except Exception:
        return False


def _require_auth(request: Request, tok: Optional[str]) -> None:
    cfg = _cfg()
    ip  = get_client_ip(request)
    check_access(ip, cfg["access"], "Admin panel")
    if not cfg["password"]:
        raise HTTPException(404, "Admin panel disabled")
    if not tok or not _verify_token(tok):
        raise HTTPException(302, headers={"Location": "/__ctrl__/login"})


# ── Dashboard HTML ────────────────────────────────────────────────────────────

_DASHBOARD = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orchestrator Control Panel</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#080810;--bg2:#0f0f1a;--bg3:#141422;--bg4:#1a1a2a;
  --border:#1a1a2a;--border2:#222233;--text:#f0f0f0;--text2:#c0c0d0;
  --dim:#888;--dimmer:#555;--green:#00ff87;--blue:#4488ff;
  --yellow:#ffcc00;--red:#ff4444;--accent:#ff6b00}
body{background:var(--bg);color:var(--text);font-family:'Courier New',monospace;
  font-size:12px;display:flex;flex-direction:column;height:100vh;overflow:hidden}

.topbar{background:#07071a;border-bottom:2px solid var(--blue);height:40px;
  display:flex;align-items:center;gap:14px;padding:0 20px;flex-shrink:0}
.tb-logo{color:var(--blue);font-size:15px;font-weight:900}
.tb-title{color:var(--text);letter-spacing:2px;font-size:10px;font-weight:700}
.tb-badge{font-size:8px;padding:2px 7px;border:1px solid rgba(68,136,255,.4);
  color:var(--blue);letter-spacing:1.5px;font-weight:700;border-radius:2px}
.tb-right{margin-left:auto;display:flex;align-items:center;gap:10px}
.tb-clock{font-size:11px;color:#aabbcc;font-variant-numeric:tabular-nums}
.tb-logout{background:transparent;border:1px solid #2a3a4a;color:#8899bb;
  padding:4px 10px;cursor:pointer;font-family:monospace;font-size:9px;
  letter-spacing:1.5px;text-transform:uppercase;text-decoration:none;
  border-radius:2px;transition:all .15s}
.tb-logout:hover{border-color:var(--red);color:var(--red)}

.layout{display:flex;flex:1;overflow:hidden}

.sidebar{width:190px;background:var(--bg2);border-right:1px solid var(--border);
  display:flex;flex-direction:column;overflow-y:auto;flex-shrink:0}
.sidebar-section{padding:14px 12px 6px;font-size:8px;color:var(--dimmer);
  letter-spacing:2px;text-transform:uppercase;font-weight:700}
.nav-item{padding:9px 14px;cursor:pointer;display:flex;align-items:center;
  gap:8px;border-left:2px solid transparent;color:var(--text2);font-size:11px;
  background:transparent;border-top:none;border-right:none;border-bottom:none;
  width:100%;text-align:left;transition:all .12s}
.nav-item:hover{background:var(--bg3);color:var(--text)}
.nav-item.active{background:var(--bg4);color:var(--blue);border-left-color:var(--blue)}
.nav-icon{font-size:12px;width:18px;text-align:center;flex-shrink:0}

.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.content-header{background:var(--bg2);border-bottom:1px solid var(--border);
  padding:10px 20px;display:flex;align-items:center;gap:12px;flex-shrink:0}
.content-title{font-size:12px;font-weight:700;letter-spacing:1.5px}
.content-sub{font-size:10px;color:var(--dim)}
.content-actions{margin-left:auto;display:flex;gap:8px}
.content-body{flex:1;overflow-y:auto;padding:16px 20px}

.tab-pane{display:none}.tab-pane.active{display:block}

/* Cards */
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px}
.card{background:var(--bg2);border:1px solid var(--border);padding:14px 16px;border-radius:2px}
.card-title{font-size:8px;letter-spacing:2.5px;color:var(--dimmer);
  text-transform:uppercase;margin-bottom:10px;font-weight:700}
.metric-value{font-size:26px;font-weight:900;color:var(--text);line-height:1}
.metric-label{font-size:9px;color:var(--dim);margin-top:4px;letter-spacing:1px}

/* Tables */
.tbl-wrap{overflow-x:auto;border:1px solid var(--border);border-radius:2px}
table{width:100%;border-collapse:collapse;font-size:11px}
th{background:var(--bg4);color:#999;padding:8px 12px;text-align:left;
  font-size:9px;letter-spacing:1.5px;text-transform:uppercase;
  border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:7px 12px;border-bottom:1px solid var(--border2);color:#ccc;
  vertical-align:middle;max-width:220px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
tr:hover td{background:var(--bg3)}

/* Badges */
.badge{display:inline-block;padding:2px 7px;border-radius:2px;font-size:9px;
  font-weight:700;letter-spacing:1px}
.badge-ok{background:rgba(0,255,135,.12);color:var(--green);border:1px solid rgba(0,255,135,.25)}
.badge-warn{background:rgba(255,204,0,.1);color:var(--yellow);border:1px solid rgba(255,204,0,.25)}
.badge-err{background:rgba(255,68,68,.1);color:var(--red);border:1px solid rgba(255,68,68,.25)}
.badge-dim{background:rgba(136,136,136,.1);color:var(--dim);border:1px solid rgba(136,136,136,.2)}

/* Buttons */
.btn{background:transparent;border:1px solid var(--border2);color:var(--dim);
  padding:5px 12px;cursor:pointer;font-family:monospace;font-size:10px;
  letter-spacing:1px;transition:all .15s;border-radius:2px}
.btn:hover{border-color:var(--blue);color:var(--blue)}
.btn-sm{padding:2px 8px;font-size:9px}

/* Log console */
.log-console{background:#050508;border:1px solid var(--border);
  height:160px;overflow-y:auto;padding:10px;font-size:10px;
  font-family:monospace;line-height:1.8}
.log-line{padding:1px 0}
.log-ok{color:var(--green)}.log-warn{color:var(--yellow)}.log-err{color:var(--red)}
.log-info{color:#7788aa}

@media(max-width:768px){
  .sidebar{position:fixed;top:40px;left:-190px;height:calc(100vh - 40px);
    z-index:200;transition:left .2s;box-shadow:4px 0 20px rgba(0,0,0,.6)}
  .sidebar.open{left:0}
  .mob-btn{display:flex!important}
  .grid-4{grid-template-columns:1fr 1fr}
}
.mob-btn{display:none;background:transparent;border:1px solid var(--border2);
  color:var(--dim);padding:4px 8px;font-size:14px;cursor:pointer;font-family:monospace}
</style></head><body>

<div class="topbar">
  <button class="mob-btn" onclick="toggleSidebar()">☰</button>
  <span class="tb-logo">⚡</span>
  <span class="tb-title">ORCHESTRATOR CTRL</span>
  <span class="tb-badge">ADMIN</span>
  <div class="tb-right">
    <span class="tb-clock" id="clock">--:--:--</span>
    <a href="/__ctrl__/logout" class="tb-logout">LOGOUT →</a>
  </div>
</div>

<div class="layout">
  <nav class="sidebar" id="sidebar">
    <div class="sidebar-section">Monitor</div>
    <button class="nav-item active" data-tab="overview"  onclick="nav('overview',this)">
      <span class="nav-icon">◉</span> Overview
    </button>
    <button class="nav-item" data-tab="sessions"  onclick="nav('sessions',this)">
      <span class="nav-icon">◈</span> Sessions
    </button>
    <button class="nav-item" data-tab="invocations" onclick="nav('invocations',this)">
      <span class="nav-icon">◎</span> Invocations
    </button>
    <button class="nav-item" data-tab="artifacts"  onclick="nav('artifacts',this)">
      <span class="nav-icon">◇</span> Artifacts
    </button>
    <div class="sidebar-section">Registry</div>
    <button class="nav-item" data-tab="agents"    onclick="nav('agents',this)">
      <span class="nav-icon">⊛</span> Agents
    </button>
  </nav>

  <div id="mob-overlay" style="display:none;position:fixed;inset:40px 0 0 0;
    background:rgba(0,0,0,.6);z-index:199" onclick="toggleSidebar()"></div>

  <main class="main">
    <!-- OVERVIEW -->
    <div id="tab-overview" class="tab-pane active">
      <div class="content-header">
        <span class="content-title">OVERVIEW</span>
        <span class="content-sub">Real-time orchestrator status</span>
        <div class="content-actions">
          <button class="btn" onclick="loadOverview()">↺ Refresh</button>
        </div>
      </div>
      <div class="content-body">
        <div class="grid-4">
          <div class="card"><div class="card-title">Total Sessions</div>
            <div class="metric-value" id="ov-sessions">—</div>
            <div class="metric-label">ALL TIME</div></div>
          <div class="card"><div class="card-title">Active Sessions</div>
            <div class="metric-value" id="ov-active" style="color:var(--green)">—</div>
            <div class="metric-label">IN PROGRESS</div></div>
          <div class="card"><div class="card-title">Total Invocations</div>
            <div class="metric-value" id="ov-invocations">—</div>
            <div class="metric-label">ALL AGENTS</div></div>
          <div class="card"><div class="card-title">Total Tokens</div>
            <div class="metric-value" id="ov-tokens">—</div>
            <div class="metric-label">INPUT+OUTPUT</div></div>
        </div>
        <div class="grid-4">
          <div class="card"><div class="card-title">Registered Agents</div>
            <div class="metric-value" id="ov-agents">—</div>
            <div class="metric-label">IN REGISTRY</div></div>
          <div class="card"><div class="card-title">Healthy Agents</div>
            <div class="metric-value" id="ov-healthy" style="color:var(--green)">—</div>
            <div class="metric-label">PASSING HEALTH CHECK</div></div>
          <div class="card"><div class="card-title">Artifacts</div>
            <div class="metric-value" id="ov-artifacts">—</div>
            <div class="metric-label">FILES</div></div>
          <div class="card"><div class="card-title">Failed Sessions</div>
            <div class="metric-value" id="ov-failed" style="color:var(--red)">—</div>
            <div class="metric-label">ERRORS</div></div>
        </div>
        <div class="card">
          <div class="card-title">RECENT SESSIONS</div>
          <div class="tbl-wrap">
            <table>
              <thead><tr>
                <th>Session ID</th><th>User</th><th>Status</th>
                <th>Agents</th><th>Tokens</th><th>Started</th><th>Duration</th>
              </tr></thead>
              <tbody id="ov-recent"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- SESSIONS -->
    <div id="tab-sessions" class="tab-pane">
      <div class="content-header">
        <span class="content-title">ORCHESTRATION SESSIONS</span>
        <span class="content-sub" id="sess-count">—</span>
        <div class="content-actions">
          <button class="btn" onclick="loadSessions()">↺ Refresh</button>
        </div>
      </div>
      <div class="content-body">
        <div class="tbl-wrap">
          <table>
            <thead><tr>
              <th>ID</th><th>Session ID</th><th>User</th><th>Status</th>
              <th>Agents</th><th>Tokens</th><th>Started</th><th>Duration</th>
            </tr></thead>
            <tbody id="sess-tbody"><tr><td colspan="8" style="text-align:center;color:var(--dim);padding:20px">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- INVOCATIONS -->
    <div id="tab-invocations" class="tab-pane">
      <div class="content-header">
        <span class="content-title">AGENT INVOCATIONS</span>
        <span class="content-sub" id="inv-count">—</span>
        <div class="content-actions">
          <input id="inv-filter" class="btn" style="width:160px;padding:5px 8px"
            placeholder="filter agent name…" oninput="filterInvocations()">
          <button class="btn" onclick="loadInvocations()">↺ Refresh</button>
        </div>
      </div>
      <div class="content-body">
        <div class="tbl-wrap">
          <table>
            <thead><tr>
              <th>ID</th><th>Agent</th><th>Status</th><th>Step</th>
              <th>Input Tok</th><th>Output Tok</th><th>Total Tok</th>
              <th>Duration</th><th>Session</th>
            </tr></thead>
            <tbody id="inv-tbody"><tr><td colspan="9" style="text-align:center;color:var(--dim);padding:20px">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ARTIFACTS -->
    <div id="tab-artifacts" class="tab-pane">
      <div class="content-header">
        <span class="content-title">ARTIFACTS</span>
        <span class="content-sub" id="art-count">—</span>
        <div class="content-actions">
          <button class="btn" onclick="loadArtifacts()">↺ Refresh</button>
        </div>
      </div>
      <div class="content-body">
        <div class="tbl-wrap">
          <table>
            <thead><tr>
              <th>File ID</th><th>Filename</th><th>Invocation</th><th>Created</th><th>Path</th>
            </tr></thead>
            <tbody id="art-tbody"><tr><td colspan="5" style="text-align:center;color:var(--dim);padding:20px">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- AGENTS -->
    <div id="tab-agents" class="tab-pane">
      <div class="content-header">
        <span class="content-title">AGENT REGISTRY</span>
        <span class="content-sub" id="ag-count">—</span>
        <div class="content-actions">
          <button class="btn" onclick="loadAgents()">↺ Refresh</button>
        </div>
      </div>
      <div class="content-body">
        <div class="tbl-wrap">
          <table>
            <thead><tr>
              <th>Name</th><th>Host</th><th>Port</th>
              <th>Active</th><th>Healthy</th><th>Last Check</th>
            </tr></thead>
            <tbody id="ag-tbody"><tr><td colspan="6" style="text-align:center;color:var(--dim);padding:20px">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>
  </main>
</div>

<script>
const BASE = '/__ctrl__/api';
let INV_DATA = [];

function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

async function api(path) {
  try {
    const r = await fetch(BASE + path, { credentials:'include' });
    if (r.status === 302 || r.status === 401) { location.href='/__ctrl__/login'; return null; }
    if (!r.ok) return null;
    return await r.json();
  } catch(e) { console.error(e); return null; }
}

function fmtNum(n) { return n == null ? '—' : Number(n).toLocaleString(); }
function fmtAgo(iso) {
  if (!iso) return '—';
  const s = Math.round((Date.now() - new Date(iso)) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s/60)}m ago`;
  return `${Math.round(s/3600)}h ago`;
}
function fmtDur(a, b) {
  if (!a || !b) return '—';
  const ms = new Date(b) - new Date(a);
  if (ms < 0) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms/1000).toFixed(1)}s`;
  return `${(ms/60000).toFixed(1)}m`;
}
function statusBadge(s) {
  const cls = {active:'badge-warn',working:'badge-warn',completed:'badge-ok',
               failed:'badge-err',cancelled:'badge-err'}[s] || 'badge-dim';
  return `<span class="badge ${cls}">${esc(s||'?')}</span>`;
}

// ── Overview ─────────────────────────────────────────────────────────────────
async function loadOverview() {
  const d = await api('/overview');
  if (!d) return;
  document.getElementById('ov-sessions').textContent    = fmtNum(d.total_sessions);
  document.getElementById('ov-active').textContent      = fmtNum(d.active_sessions);
  document.getElementById('ov-invocations').textContent = fmtNum(d.total_invocations);
  document.getElementById('ov-tokens').textContent      = fmtNum(d.total_tokens);
  document.getElementById('ov-agents').textContent      = fmtNum(d.total_agents);
  document.getElementById('ov-healthy').textContent     = fmtNum(d.healthy_agents);
  document.getElementById('ov-artifacts').textContent   = fmtNum(d.total_artifacts);
  document.getElementById('ov-failed').textContent      = fmtNum(d.failed_sessions);

  document.getElementById('ov-recent').innerHTML = (d.recent_sessions||[]).map(s => `<tr>
    <td><code style="font-size:9px;color:var(--dim)">${esc(s.session_id?.slice(0,16))}…</code></td>
    <td>${esc(s.user_id?.split('_').slice(-1)[0]||s.user_id)}</td>
    <td>${statusBadge(s.status)}</td>
    <td style="color:var(--yellow)">${fmtNum(s.agent_count)}</td>
    <td style="color:var(--blue)">${fmtNum(s.total_tokens)}</td>
    <td style="color:var(--dim);font-size:9px">${fmtAgo(s.created_at)}</td>
    <td style="color:var(--dim);font-size:9px">${fmtDur(s.created_at,s.completed_at)}</td>
  </tr>`).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--dim);padding:16px">No sessions yet</td></tr>';
}

// ── Sessions ─────────────────────────────────────────────────────────────────
async function loadSessions() {
  const d = await api('/sessions');
  if (!d) return;
  const rows = d.sessions || [];
  document.getElementById('sess-count').textContent = `${rows.length} sessions`;
  document.getElementById('sess-tbody').innerHTML = rows.map(s => `<tr>
    <td style="color:var(--dim)">${s.id}</td>
    <td><code style="font-size:9px">${esc(s.session_id?.slice(0,20))}…</code></td>
    <td>${esc(s.user_id)}</td>
    <td>${statusBadge(s.status)}</td>
    <td style="color:var(--yellow)">${fmtNum(s.agent_count)}</td>
    <td style="color:var(--blue)">${fmtNum(s.total_tokens)}</td>
    <td style="font-size:9px;color:var(--dim)">${fmtAgo(s.created_at)}</td>
    <td style="font-size:9px;color:var(--dim)">${fmtDur(s.created_at,s.completed_at)}</td>
  </tr>`).join('') || '<tr><td colspan="8" style="text-align:center;color:var(--dim);padding:20px">No sessions</td></tr>';
}

// ── Invocations ───────────────────────────────────────────────────────────────
async function loadInvocations() {
  const d = await api('/invocations');
  if (!d) return;
  INV_DATA = d.invocations || [];
  document.getElementById('inv-count').textContent = `${INV_DATA.length} invocations`;
  renderInvocations();
}
function renderInvocations() {
  const q = (document.getElementById('inv-filter').value || '').toLowerCase();
  const rows = INV_DATA.filter(i => !q || (i.agent_name||'').toLowerCase().includes(q));
  document.getElementById('inv-tbody').innerHTML = rows.map(i => `<tr>
    <td style="color:var(--dim)">${i.id}</td>
    <td style="color:var(--blue);font-weight:700">${esc(i.agent_name)}</td>
    <td>${statusBadge(i.status)}</td>
    <td style="color:var(--dim)">${i.step_order}</td>
    <td style="color:var(--yellow)">${fmtNum(i.input_tokens)}</td>
    <td style="color:var(--green)">${fmtNum(i.output_tokens)}</td>
    <td style="color:var(--blue)">${fmtNum(i.total_tokens)}</td>
    <td style="font-size:9px;color:var(--dim)">${fmtDur(i.started_at,i.completed_at)}</td>
    <td style="font-size:9px;color:var(--dim)">${i.orchestration_session_id}</td>
  </tr>`).join('') || '<tr><td colspan="9" style="text-align:center;color:var(--dim);padding:20px">No invocations</td></tr>';
}
function filterInvocations() { renderInvocations(); }

// ── Artifacts ─────────────────────────────────────────────────────────────────
async function loadArtifacts() {
  const d = await api('/artifacts');
  if (!d) return;
  const rows = d.artifacts || [];
  document.getElementById('art-count').textContent = `${rows.length} files`;
  document.getElementById('art-tbody').innerHTML = rows.map(a => `<tr>
    <td><code style="font-size:9px;color:var(--dim)">${esc(a.file_id?.slice(0,12))}</code></td>
    <td style="color:var(--blue)">${esc(a.filename)}</td>
    <td style="color:var(--dim)">${a.invocation_id}</td>
    <td style="font-size:9px;color:var(--dim)">${fmtAgo(a.created_at)}</td>
    <td><code style="font-size:9px;color:var(--dimmer)">${esc((a.path||'').slice(-40))}</code></td>
  </tr>`).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--dim);padding:20px">No artifacts</td></tr>';
}

// ── Agents ────────────────────────────────────────────────────────────────────
async function loadAgents() {
  const d = await api('/agents');
  if (!d) return;
  const rows = d.agents || [];
  document.getElementById('ag-count').textContent = `${rows.length} agents`;
  document.getElementById('ag-tbody').innerHTML = rows.map(a => `<tr>
    <td style="color:var(--blue);font-weight:700">${esc(a.name)}</td>
    <td><code style="font-size:9px">${esc(a.host)}</code></td>
    <td>${a.port}</td>
    <td>${a.is_active
      ? '<span class="badge badge-ok">active</span>'
      : '<span class="badge badge-dim">inactive</span>'}</td>
    <td>${a.is_healthy
      ? '<span class="badge badge-ok">healthy</span>'
      : '<span class="badge badge-err">unhealthy</span>'}</td>
    <td style="font-size:9px;color:var(--dim)">${fmtAgo(a.last_health_check)}</td>
  </tr>`).join('') || '<tr><td colspan="6" style="text-align:center;color:var(--dim);padding:20px">No agents registered</td></tr>';
}

// ── Navigation ────────────────────────────────────────────────────────────────
const LOADERS = {
  overview:   loadOverview,
  sessions:   loadSessions,
  invocations:loadInvocations,
  artifacts:  loadArtifacts,
  agents:     loadAgents,
};

function nav(name, el) {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  document.querySelectorAll('.tab-pane').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  if (LOADERS[name]) LOADERS[name]();
  if (window.innerWidth <= 768) toggleSidebar();
}

function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  const ov = document.getElementById('mob-overlay');
  const open = sb.classList.toggle('open');
  ov.style.display = open ? '' : 'none';
}

// ── Clock ─────────────────────────────────────────────────────────────────────
setInterval(() => {
  document.getElementById('clock').textContent =
    new Date().toLocaleTimeString('en-GB');
}, 1000);

// ── Init ──────────────────────────────────────────────────────────────────────
loadOverview();
</script></body></html>"""

_LOGIN_HTML = """\
<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orchestrator Panel — Login</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#080810;color:#e0e0e0;font-family:'Courier New',monospace;
  display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#0f0f1a;border:1px solid #1a1a2a;padding:48px 40px;width:400px}
.logo{color:#4488ff;font-size:22px;font-weight:900;letter-spacing:2px;margin-bottom:6px}
.sub{color:#333;font-size:9px;letter-spacing:3px;margin-bottom:32px}
label{display:block;font-size:9px;color:#666;letter-spacing:2px;
  text-transform:uppercase;margin-bottom:6px;margin-top:18px}
input[type=password]{width:100%;background:#080810;border:1px solid #222;color:#e0e0e0;
  font-family:monospace;font-size:13px;padding:10px 14px;outline:none}
input[type=password]:focus{border-color:#4488ff}
button{width:100%;margin-top:24px;background:#4488ff;color:#fff;border:none;
  padding:12px;font-family:monospace;font-size:12px;font-weight:700;
  letter-spacing:2px;text-transform:uppercase;cursor:pointer}
button:hover{opacity:.85}
.err{color:#ff4444;font-size:11px;margin-top:12px;padding:8px 12px;
  background:#1a0000;border:1px solid rgba(255,68,68,.25)}
</style></head><body><div class="card">
  <div class="logo">⚡ ORCHESTRATOR</div>
  <div class="sub">ADMIN CONTROL PANEL</div>
  <form method="POST" action="/__ctrl__/login">
    <label>Password</label>
    <input type="password" name="password" autofocus autocomplete="current-password">
    ERR
    <button type="submit">ACCESS PANEL →</button>
  </form>
</div></body></html>"""


# ── ASGI sub-app ──────────────────────────────────────────────────────────────

orch_panel_app = FastAPI(
    title="Orchestrator Admin Panel",
    docs_url=None, redoc_url=None, openapi_url=None,
)


@orch_panel_app.get("/login", response_class=HTMLResponse)
async def panel_login(request: Request):
    cfg = _cfg()
    ip  = get_client_ip(request)
    check_access(ip, cfg["access"], "Admin panel")
    return HTMLResponse(_LOGIN_HTML.replace("ERR", ""))


@orch_panel_app.post("/login")
async def panel_login_submit(request: Request, password: str = Form(...)):
    cfg = _cfg()
    ip  = get_client_ip(request)
    check_access(ip, cfg["access"], "Admin panel")
    if not cfg["password"]:
        raise HTTPException(404, "Disabled")
    if not hmac.compare_digest(password.encode(), cfg["password"].encode()):
        return HTMLResponse(_LOGIN_HTML.replace(
            "ERR", '<div class="err">❌ Incorrect password</div>'), 401)
    resp = RedirectResponse("/__ctrl__/", status_code=303)
    resp.set_cookie(COOKIE, _make_token(),
                    httponly=True, samesite="lax", secure=False, path="/__ctrl__")
    return resp


@orch_panel_app.get("/logout")
async def panel_logout():
    resp = RedirectResponse("/__ctrl__/login", status_code=303)
    resp.delete_cookie(COOKIE, path="/__ctrl__")
    return resp


@orch_panel_app.get("/", response_class=HTMLResponse)
async def panel_dashboard(request: Request, *,
                           __orch_ctrl: Optional[str] = Cookie(default=None)):
    cfg = _cfg()
    ip  = get_client_ip(request)
    check_access(ip, cfg["access"], "Admin panel")
    if not cfg["password"]:
        raise HTTPException(404, "Disabled")
    if not __orch_ctrl or not _verify_token(__orch_ctrl):
        return RedirectResponse("/__ctrl__/login", status_code=302)
    return HTMLResponse(_DASHBOARD)


# ── API endpoints ─────────────────────────────────────────────────────────────

def _auth(request: Request, tok: Optional[str]) -> None:
    cfg = _cfg()
    ip  = get_client_ip(request)
    check_access(ip, cfg["access"], "Admin panel")
    if not tok or not _verify_token(tok):
        raise HTTPException(401, "Session expired")


@orch_panel_app.get("/api/overview")
async def api_overview(request: Request, *,
                       __orch_ctrl: Optional[str] = Cookie(default=None)):
    _auth(request, __orch_ctrl)
    try:
        from sqlalchemy import select, func, text
        from database.session import AsyncSessionLocal
        from database.models import (OrchestrationSession, AgentInvocation,
                                     AgentRegistry, Artifact)
        async with AsyncSessionLocal() as db:
            total_sess   = (await db.execute(select(func.count(OrchestrationSession.id)))).scalar() or 0
            active_sess  = (await db.execute(select(func.count(OrchestrationSession.id))
                           .where(OrchestrationSession.status == "active"))).scalar() or 0
            failed_sess  = (await db.execute(select(func.count(OrchestrationSession.id))
                           .where(OrchestrationSession.status == "failed"))).scalar() or 0
            total_inv    = (await db.execute(select(func.count(AgentInvocation.id)))).scalar() or 0
            total_tok    = (await db.execute(select(func.sum(AgentInvocation.total_tokens)))).scalar() or 0
            total_agents = (await db.execute(select(func.count(AgentRegistry.id)))).scalar() or 0
            healthy      = (await db.execute(select(func.count(AgentRegistry.id))
                           .where(AgentRegistry.is_healthy == True))).scalar() or 0
            total_art    = (await db.execute(select(func.count(Artifact.id)))).scalar() or 0

            # Recent sessions with aggregate token/agent counts
            recent_q = await db.execute(
                select(
                    OrchestrationSession,
                    func.count(AgentInvocation.id).label("agent_count"),
                    func.sum(AgentInvocation.total_tokens).label("total_tokens"),
                )
                .outerjoin(AgentInvocation,
                           AgentInvocation.orchestration_session_id == OrchestrationSession.id)
                .group_by(OrchestrationSession.id)
                .order_by(OrchestrationSession.id.desc())
                .limit(10)
            )
            recent = []
            for row in recent_q:
                s = row[0]
                recent.append({
                    "session_id": s.session_id,
                    "user_id": s.user_id,
                    "status": s.status,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "agent_count": row[1] or 0,
                    "total_tokens": int(row[2] or 0),
                })
        return {
            "total_sessions": total_sess,   "active_sessions": active_sess,
            "failed_sessions": failed_sess, "total_invocations": total_inv,
            "total_tokens": int(total_tok), "total_agents": total_agents,
            "healthy_agents": healthy,      "total_artifacts": total_art,
            "recent_sessions": recent,
        }
    except Exception as e:
        return {"error": str(e), "recent_sessions": []}


@orch_panel_app.get("/api/sessions")
async def api_sessions(request: Request, *,
                       __orch_ctrl: Optional[str] = Cookie(default=None)):
    _auth(request, __orch_ctrl)
    try:
        from sqlalchemy import select, func
        from database.session import AsyncSessionLocal
        from database.models import OrchestrationSession, AgentInvocation
        async with AsyncSessionLocal() as db:
            q = await db.execute(
                select(
                    OrchestrationSession,
                    func.count(AgentInvocation.id).label("agent_count"),
                    func.sum(AgentInvocation.total_tokens).label("total_tokens"),
                )
                .outerjoin(AgentInvocation,
                           AgentInvocation.orchestration_session_id == OrchestrationSession.id)
                .group_by(OrchestrationSession.id)
                .order_by(OrchestrationSession.id.desc())
                .limit(200)
            )
            sessions = []
            for row in q:
                s = row[0]
                sessions.append({
                    "id": s.id, "session_id": s.session_id, "user_id": s.user_id,
                    "status": s.status,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "agent_count": row[1] or 0,
                    "total_tokens": int(row[2] or 0),
                })
        return {"sessions": sessions}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


@orch_panel_app.get("/api/invocations")
async def api_invocations(request: Request, *,
                          __orch_ctrl: Optional[str] = Cookie(default=None)):
    _auth(request, __orch_ctrl)
    try:
        from sqlalchemy import select
        from database.session import AsyncSessionLocal
        from database.models import AgentInvocation
        async with AsyncSessionLocal() as db:
            q = await db.execute(
                select(AgentInvocation)
                .order_by(AgentInvocation.id.desc())
                .limit(300)
            )
            rows = q.scalars().all()
            invocations = [{
                "id": i.id,
                "orchestration_session_id": i.orchestration_session_id,
                "agent_name": i.agent_name,
                "agent_session_id": i.agent_session_id,
                "step_order": i.step_order,
                "status": i.status,
                "input_tokens": i.input_tokens,
                "output_tokens": i.output_tokens,
                "total_tokens": i.total_tokens,
                "started_at": i.started_at.isoformat() if i.started_at else None,
                "completed_at": i.completed_at.isoformat() if i.completed_at else None,
            } for i in rows]
        return {"invocations": invocations}
    except Exception as e:
        return {"invocations": [], "error": str(e)}


@orch_panel_app.get("/api/artifacts")
async def api_artifacts(request: Request, *,
                        __orch_ctrl: Optional[str] = Cookie(default=None)):
    _auth(request, __orch_ctrl)
    try:
        from sqlalchemy import select
        from database.session import AsyncSessionLocal
        from database.models import Artifact
        async with AsyncSessionLocal() as db:
            q = await db.execute(
                select(Artifact).order_by(Artifact.id.desc()).limit(200)
            )
            rows = q.scalars().all()
            artifacts = [{
                "id": a.id, "invocation_id": a.invocation_id,
                "file_id": a.file_id, "filename": a.filename,
                "path": a.path,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            } for a in rows]
        return {"artifacts": artifacts}
    except Exception as e:
        return {"artifacts": [], "error": str(e)}


@orch_panel_app.get("/api/agents")
async def api_agents(request: Request, *,
                     __orch_ctrl: Optional[str] = Cookie(default=None)):
    _auth(request, __orch_ctrl)
    try:
        from sqlalchemy import select
        from database.session import AsyncSessionLocal
        from database.models import AgentRegistry
        async with AsyncSessionLocal() as db:
            q = await db.execute(select(AgentRegistry).order_by(AgentRegistry.id))
            rows = q.scalars().all()
            agents = [{
                "id": a.id, "name": a.name, "host": a.host, "port": a.port,
                "is_active": a.is_active, "is_healthy": a.is_healthy,
                "last_health_check": a.last_health_check.isoformat()
                                     if a.last_health_check else None,
            } for a in rows]
        return {"agents": agents}
    except Exception as e:
        return {"agents": [], "error": str(e)}
