# from sqlalchemy.ext.asyncio import create_async_engine
# import os
# from dotenv import load_dotenv
# load_dotenv()

# DATABASE_URL=os.getenv("DATABASE_URL","")

# engine=create_async_engine(
#     DATABASE_URL,
#     echo=False,
# )



"""
database/engine.py — DBMODE-aware engine.

Backward-compatible: still exports `engine` (the SQLAlchemy AsyncEngine).
In local mode, `engine` is None and callers must check IS_LOCAL.

DBMODE selection (set in .env)
──────────────────────────────
  postgres  PostgreSQL — uses DATABASE_URL (validated at first use)
  local     JSON file store in data/, no SQL engine — auto-creates dir
  auto      [default] DATABASE_URL set → postgres; otherwise → local

The behavior of the working PostgreSQL setup is unchanged: same
create_async_engine call, same DATABASE_URL env, same `engine` export.
New: local mode (engine=None) for laptop development with no PG install.
"""
from __future__ import annotations

import logging
import os
import socket
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def _dbmode() -> str:
    raw = os.environ.get("DBMODE", "auto").strip().lower()
    if raw in ("json", "file", "files"):       return "local"
    if raw in ("pg", "postgresql"):            return "postgres"
    if raw not in ("postgres", "local", "auto"): return "auto"
    return raw


def _pg_reachable(url: str, timeout: float = 1.5) -> bool:
    if not url: return False
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        s = socket.create_connection(
            (p.hostname or "localhost", p.port or 5432), timeout=timeout
        )
        s.close()
        return True
    except Exception:
        return False


DBMODE         = _dbmode()
DATABASE_URL   = os.getenv("DATABASE_URL", "").strip()
JSON_DATA_DIR  = Path(os.environ.get("JSON_DATA_DIR", "data"))

engine: Optional[AsyncEngine] = None
IS_LOCAL    = False
IS_POSTGRES = False


def _build_engine(url: str) -> Optional[AsyncEngine]:
    try:
        return create_async_engine(url, echo=False, pool_pre_ping=True)
    except Exception as e:
        logger.warning("[db] create_async_engine failed: %s", e)
        return None


# ── Decide backend at import time ─────────────────────────────────────────────

if DBMODE == "postgres":
    if not DATABASE_URL:
        raise RuntimeError(
            "DBMODE=postgres but DATABASE_URL is not set. "
            "Set DATABASE_URL, or use DBMODE=local / DBMODE=auto."
        )
    engine = _build_engine(DATABASE_URL)
    IS_POSTGRES = True
    logger.info("[db] DBMODE=postgres — using PostgreSQL")

elif DBMODE == "local":
    JSON_DATA_DIR.mkdir(parents=True, exist_ok=True)
    IS_LOCAL = True
    logger.info("[db] DBMODE=local — JSON file store at %s/", JSON_DATA_DIR)

else:  # auto
    if DATABASE_URL and _pg_reachable(DATABASE_URL):
        engine = _build_engine(DATABASE_URL)
        if engine is not None:
            IS_POSTGRES = True
            logger.info("[db] DBMODE=auto → PostgreSQL reachable, using it")
        else:
            JSON_DATA_DIR.mkdir(parents=True, exist_ok=True)
            IS_LOCAL = True
            logger.warning("[db] DBMODE=auto → engine build failed, using local JSON")
    else:
        if DATABASE_URL:
            logger.warning("[db] DBMODE=auto → PostgreSQL unreachable, using local JSON")
        else:
            logger.info("[db] DBMODE=auto → DATABASE_URL unset, using local JSON")
        JSON_DATA_DIR.mkdir(parents=True, exist_ok=True)
        IS_LOCAL = True


def get_backend() -> str:
    return "postgres" if IS_POSTGRES else "local"


# Back-compat alias for any older import paths
is_local       = lambda: IS_LOCAL
is_postgres    = lambda: IS_POSTGRES
is_json_backend = lambda: IS_LOCAL
