"""Database access helpers.

This module exposes small convenience wrappers around the SQLite
database shipped with the project.  The functions are intentionally
simple so the frontend can call them through API routes without having
to know anything about SQL.
"""
# packages/api/src/db.py

from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Any
# The database file lives in ``storage`` next to this module.  Using a
# resolved path makes it work no matter where the code is executed from.
DB_PATH = Path(__file__).resolve().parent / "storage" / "game_data.db"


def _connect() -> sqlite3.Connection:
    """Return a connection with rows accessible as dictionaries."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _fetch_all(cursor: sqlite3.Cursor) -> List[Dict[str, object]]:
    """Convert a cursor's remaining rows to a list of plain dictionaries."""
    return [dict(row) for row in cursor.fetchall()]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Check whether a table exists in the database."""
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    return cur.fetchone() is not None

def fetch_saves(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return rows from the `Saves` table, ordered by saved_at descending."""
    with _connect() as conn:
        if not _table_exists(conn, "Saves"):
            return []
        cur = conn.cursor()
        query = "SELECT * FROM Saves ORDER BY saved_at DESC"
        if limit:
            query += " LIMIT ?"
            cur.execute(query, (limit,))
        else:
            cur.execute(query)
        return _fetch_all(cur)


def fetch_countries(save_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return rows from the `Countries` table, optionally filtered by save_id."""
    with _connect() as conn:
        if not _table_exists(conn, "Countries"):
            return []
        cur = conn.cursor()
        if save_id:
            cur.execute(
                "SELECT * FROM Countries WHERE save_id=?",
                (save_id,)
            )
        else:
            cur.execute("SELECT * FROM Countries")
        return _fetch_all(cur)


def fetch_wars(save_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return rows from `Wars`, optionally filtering by save_id and/or status."""
    with _connect() as conn:
        if not _table_exists(conn, "Wars"):
            return []
        cur = conn.cursor()
        clauses: List[str] = []
        params: List[Any] = []
        if save_id:
            clauses.append("save_id=?"); params.append(save_id)
        if status:
            clauses.append("status=?"); params.append(status)
        sql = "SELECT * FROM Wars"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_on DESC"
        cur.execute(sql, params)
        return _fetch_all(cur)


def fetch_war_participants(war_id: str) -> List[Dict[str, Any]]:
    """Return participants for a given war_id."""
    with _connect() as conn:
        if not _table_exists(conn, "War_Participants"):
            return []
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM War_Participants WHERE war_id=?",
            (war_id,)
        )
        return _fetch_all(cur)


def fetch_battles(war_id: Optional[str] = None, country_tag: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return rows from `Battles`, optionally filtering by war_id or involved country_tag."""
    with _connect() as conn:
        if not _table_exists(conn, "Battles"):
            return []
        cur = conn.cursor()
        clauses: List[str] = []
        params: List[Any] = []
        if war_id:
            clauses.append("war_id=?"); params.append(war_id)
        if country_tag:
            clauses.append("(attacker_tag=? OR defender_tag=?)"); params.extend([country_tag, country_tag])
        sql = "SELECT * FROM Battles"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY occurred_on DESC"
        cur.execute(sql, params)
        return _fetch_all(cur)


def fetch_country_metrics(
    country_tag: str,
    metric_name: Optional[str] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Return rows from `CountryMetrics` for a country, optional metric filter and limit."""
    with _connect() as conn:
        if not _table_exists(conn, "CountryMetrics"):
            return []
        cur = conn.cursor()
        clauses = ["country_tag=?"]
        params: List[Any] = [country_tag]
        if metric_name:
            clauses.append("name=?"); params.append(metric_name)
        sql = (
            "SELECT * FROM CountryMetrics WHERE " + " AND ".join(clauses)
            + " ORDER BY recorded_at DESC"
        )
        if limit:
            sql += " LIMIT ?"; params.append(limit)
        cur.execute(sql, params)
        return _fetch_all(cur)

__all__ = [
    "fetch_saves",
    "fetch_countries",
    "fetch_wars",
    "fetch_war_participants",
    "fetch_battles",
    "fetch_country_metrics",
]