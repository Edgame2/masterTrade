#!/usr/bin/env python3
"""Utility script to apply the consolidated PostgreSQL schema.

This script reads the SQL definitions from ``postgres/schema.sql`` and applies
them to a target PostgreSQL database using ``asyncpg``. Connection parameters
can be supplied via CLI flags or environment variables (POSTGRES_*)."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Iterable

import asyncpg

DEFAULT_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _env_or_default(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is not None and value.strip() != "":
        return value
    return default


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply the MasterTrade PostgreSQL schema to a database.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dsn",
        help=(
            "Full PostgreSQL DSN. If provided, host/port/user/password/database "
            "arguments are ignored."
        ),
        default=_env_or_default("POSTGRES_DSN"),
    )
    parser.add_argument(
        "--host",
        default=_env_or_default("POSTGRES_HOST", "localhost"),
        help="PostgreSQL server host.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(_env_or_default("POSTGRES_PORT", "5432")),
        help="PostgreSQL server port.",
    )
    parser.add_argument(
        "--user",
        default=_env_or_default("POSTGRES_USER", "mastertrade"),
        help="Database user.",
    )
    parser.add_argument(
        "--password",
        default=_env_or_default("POSTGRES_PASSWORD", "mastertrade"),
        help="Database user password.",
    )
    parser.add_argument(
        "--database",
        default=_env_or_default("POSTGRES_DB", "mastertrade"),
        help="Target database name.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help="Path to the schema SQL file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the SQL statements without executing them.",
    )
    return parser


def _build_dsn(args: argparse.Namespace) -> str:
    if args.dsn:
        return args.dsn
    password_part = f":{args.password}" if args.password else ""
    return f"postgresql://{args.user}{password_part}@{args.host}:{args.port}/{args.database}"


def _load_statements(schema_path: Path) -> Iterable[str]:
    raw_sql = schema_path.read_text(encoding="utf-8")
    statements = []
    for statement in raw_sql.split(";"):
        cleaned = statement.strip()
        if cleaned:
            statements.append(cleaned)
    return statements


async def _apply_schema(dsn: str, statements: Iterable[str]) -> None:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        for statement in statements:
            await conn.execute(statement)
    finally:
        await conn.close()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.schema.exists():
        raise FileNotFoundError(f"Schema file not found: {args.schema}")

    statements = list(_load_statements(args.schema))
    if not statements:
        raise ValueError(f"No SQL statements found in {args.schema}")

    if args.dry_run:
        for statement in statements:
            print(f"\n-- Statement --\n{statement}\n")
        print(f"Total statements: {len(statements)}")
        return

    dsn = _build_dsn(args)
    print(f"Applying schema from {args.schema} to {dsn}")
    try:
        asyncio.run(_apply_schema(dsn, statements))
    except asyncpg.PostgresError as exc:
        raise SystemExit(f"Failed to apply schema: {exc}") from exc
    else:
        print("Schema applied successfully.")


if __name__ == "__main__":
    main()
