import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "data.db"
PERSISTENT_DATA_DIR = Path("/data")
BACKUP_PATH = Path.home() / ".desk-booking" / "desks.json"

def _secret_db_path() -> str | None:
    if not hasattr(st, "secrets"):
        return None

    db_path = st.secrets.get("db_path")
    if db_path:
        return db_path

    db_config = st.secrets.get("database")
    if isinstance(db_config, dict):
        return db_config.get("path")

    return None

def _resolve_db_path() -> Path:
    env_path = os.getenv("DESK_BOOKING_DB_PATH")
    if env_path:
        return Path(env_path)

    secret_path = _secret_db_path()
    if secret_path:
        return Path(secret_path)

    if DEFAULT_DB_PATH.exists():
        return DEFAULT_DB_PATH

    if PERSISTENT_DATA_DIR.is_dir():
        return PERSISTENT_DATA_DIR / "desk-booking.db"

    return Path.home() / ".desk-booking" / "data.db"

DB_PATH = _resolve_db_path().expanduser()

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)

def _load_desks_backup():
    if not BACKUP_PATH.exists():
        return []

    try:
        return json.loads(BACKUP_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

def write_desks_backup():
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
            "name": name,
            "location": location,
            "is_active": is_active,
            "admin_only": admin_only,
        }
        for name, location, is_active, admin_only in desks
    ]

    BACKUP_PATH.write_text(
        json.dumps(backup_data, indent=2),
        encoding="utf-8",
    )

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ---------------------------------------------------
    # USERS TABLE
    # ---------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            role TEXT,
            can_book INTEGER,
            is_active INTEGER DEFAULT 1
        )
    """)

    # ---------------------------------------------------
    # DESKS TABLE
    # ---------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS desks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT,
            is_active INTEGER DEFAULT 1,
            admin_only INTEGER DEFAULT 0
        )
    """)

    # ---------------------------------------------------
    # AUDIT LOG TABLE
    # ---------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            action TEXT,
            details TEXT,
            timestamp TEXT
        )
    """)

    conn.commit()
    conn.close()
