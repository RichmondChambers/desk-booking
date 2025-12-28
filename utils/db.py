import json
import sqlite3
from pathlib import Path

import streamlit as st


# ===================================================
# SINGLE, IMMUTABLE DATABASE LOCATION (PERSISTENT)
# ===================================================

DB_PATH = Path("/data/desk-booking.db")
DESK_BACKUP_PATH = Path("/data/desks.json")

# Fail fast if persistence is unavailable
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
if not DB_PATH.parent.is_dir():
    raise RuntimeError("Persistent /data volume is not available")

DESK_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)


# ===================================================
# DATABASE CONNECTION
# ===================================================

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Critical durability settings
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")

    return conn


# ===================================================
# DATABASE INITIALISATION
# ===================================================

def init_db() -> None:
    conn = get_conn()
    c = conn.cursor()

    # USERS
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            role TEXT,
            can_book INTEGER,
            is_active INTEGER DEFAULT 1
        )
        """
    )

    # DESKS
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS desks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT,
            is_active INTEGER DEFAULT 1,
            admin_only INTEGER DEFAULT 0
        )
        """
    )

    # BOOKINGS (PERSISTENT & SAFE)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            desk_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL,
            checked_in INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (desk_id) REFERENCES desks(id)
        )
        """
    )

    # AUDIT LOG
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            action TEXT,
            details TEXT,
            timestamp TEXT
        )
        """
    )

    conn.commit()
    conn.close()


# ===================================================
# DESK BACKUP HANDLING
# ===================================================

def _load_desks_backup() -> list[dict]:
    if not DESK_BACKUP_PATH.exists():
        return []

    try:
        return json.loads(DESK_BACKUP_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def write_desks_backup() -> None:
    conn = get_conn()
    desks = conn.execute(
        """
        SELECT name, location, is_active, admin_only
        FROM desks
        ORDER BY id
        """
    ).fetchall()
    conn.close()

    backup_data = [
        {
            "name": row["name"],
            "location": row["location"],
            "is_active": row["is_active"],
            "admin_only": row["admin_only"],
        }
        for row in desks
    ]

    DESK_BACKUP_PATH.write_text(
        json.dumps(backup_data, indent=2),
        encoding="utf-8",
    )


# ===================================================
# SEED DEFAULT DESKS (SAFE & IDEMPOTENT)
# ===================================================

def seed_desks() -> None:
    default_desks = [
        {"name": f"Desk {i}", "location": "Office", "admin_only": 0}
        for i in range(1, 13)
    ] + [
        {"name": f"Desk {i}", "location": "Admin", "admin_only": 1}
        for i in range(13, 16)
    ]

    conn = get_conn()
    c = conn.cursor()

    existing = c.execute("SELECT name FROM desks").fetchall()
    existing_names = {row["name"] for row in existing}

    backup_desks = _load_desks_backup()

    for desk in backup_desks:
        if desk["name"] not in existing_names:
            c.execute(
                """
                INSERT INTO desks (name, location, is_active, admin_only)
                VALUES (?, ?, ?, ?)
                """,
                (
                    desk["name"],
                    desk.get("location"),
                    desk.get("is_active", 1),
                    desk.get("admin_only", 0),
                ),
            )

    for desk in default_desks:
        if desk["name"] not in existing_names:
            c.execute(
                """
                INSERT INTO desks (name, location, is_active, admin_only)
                VALUES (?, ?, ?, ?)
                """,
                (desk["name"], desk["location"], 1, desk["admin_only"]),
            )

    conn.commit()
    conn.close()

    write_desks_backup()


# ===================================================
# ENTRYPOINT
# ===================================================

def ensure_db() -> None:
    init_db()
    seed_desks()
