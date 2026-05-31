"""
database/json_store.py — Local JSON file store for chat history.

Mirrors the pattern used by the tenant service's local-json backend.
Each "table" is a JSON file under JSON_DATA_DIR. Atomic writes
(temp file → rename). One asyncio.Lock per file to prevent torn writes.

Used when DBMODE=local (or DBMODE=auto falls back to local).
Only the chat-history feature uses this store; the existing PostgreSQL
path is unaffected.

Tables
──────
  jdb.sessions   chat_sessions.json    one row per conversation
  jdb.messages   chat_messages.json    one row per message
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Callable, Dict, List, Optional, Tuple

_DATA_DIR = Path(os.environ.get("JSON_DATA_DIR", "data"))


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic_write(path: Path, data: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, default=str, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read(path: Path) -> list:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")) or []
    except Exception:
        return []


class JsonTable:
    """Simple file-backed list of dicts. Thread- and asyncio-safe within
    one process (the orchestrator is single-process by default)."""

    def __init__(self, filename: str):
        self._path: Path = _DATA_DIR / filename
        self._rows: Optional[List[Dict]] = None
        self._next_id = 1
        self._lock = RLock()

    # ── internal ──────────────────────────────────────────────────────────────

    def _load(self) -> List[Dict]:
        if self._rows is None:
            self._rows = _read(self._path)
            if self._rows:
                self._next_id = max((r.get("id", 0) for r in self._rows), default=0) + 1
        return self._rows

    def _flush(self) -> None:
        _atomic_write(self._path, self._rows or [])

    # ── public ────────────────────────────────────────────────────────────────

    def insert(self, doc: Dict) -> Dict:
        with self._lock:
            rows = self._load()
            doc = {"id": self._next_id, "created_at": _iso_now(), **doc}
            self._next_id += 1
            rows.append(doc)
            self._flush()
            return doc

    def update_one(self, predicate: Callable[[Dict], bool], updates: Dict) -> bool:
        with self._lock:
            rows = self._load()
            for i, r in enumerate(rows):
                if predicate(r):
                    rows[i] = {**r, **updates}
                    self._flush()
                    return True
            return False

    def upsert(self, predicate: Callable[[Dict], bool], doc: Dict) -> Dict:
        with self._lock:
            rows = self._load()
            for i, r in enumerate(rows):
                if predicate(r):
                    rows[i] = {**r, **doc}
                    self._flush()
                    return rows[i]
            return self.insert(doc)

    def delete_where(self, predicate: Callable[[Dict], bool]) -> int:
        with self._lock:
            rows = self._load()
            before = len(rows)
            self._rows = [r for r in rows if not predicate(r)]
            self._flush()
            return before - len(self._rows)

    def find(self, predicate: Callable[[Dict], bool]) -> List[Dict]:
        return [r for r in self._load() if predicate(r)]

    def find_one(self, predicate: Callable[[Dict], bool]) -> Optional[Dict]:
        for r in self._load():
            if predicate(r):
                return r
        return None

    def paginate(
        self,
        predicate: Callable[[Dict], bool],
        sort_key: str = "created_at",
        reverse: bool = True,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Dict], int]:
        items = [r for r in self._load() if predicate(r)]
        items.sort(key=lambda r: r.get(sort_key, "") or "", reverse=reverse)
        return items[skip: skip + limit], len(items)


class _JsonDB:
    """Module-level singleton — all access via `from database.json_store import jdb`."""
    sessions = JsonTable("chat_sessions.json")
    messages = JsonTable("chat_messages.json")


jdb = _JsonDB()
