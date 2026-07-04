# memory_management/adk-base-memory/_types.py

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Dialect, Text
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.types import TypeDecorator


class DynamicJSON(TypeDecorator):
    """JSON column that uses JSONB on Postgres, LONGTEXT on MySQL, TEXT elsewhere."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.LONGTEXT())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return json.dumps(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return json.loads(value)