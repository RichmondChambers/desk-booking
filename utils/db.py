import json
import os
import sqlite3
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "data.db"
PERSISTENT_DATA_DIR = Path("/data")


# ---------------------------------------------------
# DATABASE PATH RESOLUTION
# ---------------------------------------------------
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

    persistent_candidate = PERSISTENT_DATA_DIR / "desk-booking.db"
    if PERSISTENT_DATA_DIR.is_dir() and (
        os.path.ismount(PERSISTENT_DATA_DIR) or persistent_candidate.exists()
    ):
        return persistent_candidate

    home_candidate = Path.home() / ".desk-booking" / "data.db"
    if home_candidate.exists():
        return home_candidate

    if DEFAULT_DB_PATH.exists():
        return DEFAULT_DB_PATH

    return home_candidate


DB_PATH = _resolve_db_path().expanduser()
DESK_BACKUP_PATH = Path(
    os.getenv(
        "DESK_BOOKING_DESK_BACKUP_PATH",
        DB_PATH.parent / "desks.json",
    )
).expanduser()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DESK_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------
# CONNECTION HANDLING
# ---------------------------------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------
# BACKUP HANDLING
# ---------------------------------------------------
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


# ---------------------------------------------------
# DATABASE INITIALISATION
# ---------------------------------------------------
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

    # BOOKINGS (CRITICAL)
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


# ---------------------------------------------------
# SEED DEFAULT DESKS
# ---------------------------------------------------
def seed_desks() -> None:
    """
    Insert default desks if none exist.
    Safe to run multiple times.
    """
    conn = get_conn()
    c = conn.cursor()

    existing_desks = c.execute(
        """
        SELECT id, name
        FROM desks
        """
    ).fetchall()
    existing_by_name = {row["name"]: row["id"] for row in existing_desks}
    backup_desks = _load_desks_backup()

    if backup_desks:
        for desk in backup_desks:
            name = desk.get("name")
            if not name:
                continue

            location = desk.get("location")
            is_active = desk.get("is_active", 1)
            admin_only = desk.get("admin_only", 0)
            existing_id = existing_by_name.get(name)

            if existing_id is None:
                c.execute(
                    """
                    INSERT INTO desks (name, location, is_active, admin_only)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, location, is_active, admin_only),
                )
            else:
                c.execute(
                    """
                    UPDATE desks
                    SET location = ?, is_active = ?, admin_only = ?
                    WHERE id = ?
                    """,
                    (location, is_active, admin_only, existing_id),
                )

        conn.commit()
    elif not existing_desks:
        c.executemany(
            """
            INSERT INTO desks (name, location)
            VALUES (?, ?)
            """,
            [
                ("Desk 1", "Office"),
                ("Desk 2", "Office"),
                ("Desk 3", "Office"),
            ],
        )

        conn.commit()

    conn.close()
