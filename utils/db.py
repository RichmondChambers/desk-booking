import json
import os
import sqlite3
from pathlib import Path

import streamlit as st


# ===================================================
# RESOLVE A GUARANTEED-PERSISTENT DATA DIRECTORY
# ===================================================

def _resolve_data_dir() -> tuple[Path, bool]:
    """
    Priority:
    1. Explicit DESK_BOOKING_DATA_DIR (recommended for production)
    2. Streamlit Cloud persistent volume (/data) IF writable
    3. Project-local ./data directory (only if explicitly allowed)
    Otherwise: crash (no silent data loss)
    """

    env_dir = os.getenv("DESK_BOOKING_DATA_DIR")
    allow_ephemeral = os.getenv("DESK_BOOKING_ALLOW_EPHEMERAL") == "1"

    candidates: list[tuple[Path, bool]] = []

    if env_dir:
        candidates.append((Path(env_dir).expanduser(), True))

    candidates.append((Path("/data"), True))

    if allow_ephemeral:
        candidates.append(
            (Path(__file__).resolve().parent.parent / "data", False)
        )

    for path, is_persistent in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".write_test"
            test_file.write_text("ok")
            test_file.unlink()
            return path, is_persistent
        except Exception:
            continue

    if not allow_ephemeral:
        raise RuntimeError(
            "No writable persistent data directory available. "
            "Set DESK_BOOKING_DATA_DIR or mount /data to prevent booking loss."
        )

    raise RuntimeError(
        "No writable data directory available. "
        "Bookings cannot be safely stored."
    )


# ===================================================
# PATH RESOLUTION
# ===================================================

db_path_env = os.getenv("DESK_BOOKING_DB_PATH")
if db_path_env:
    DB_PATH = Path(db_path_env).expanduser()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
else:
    DB_PATH = DATA_DIR / "desk-booking.db"

if not DB_PATH.parent.exists():
    raise RuntimeError(
        "Database directory does not exist or is not writable."
    )

DESK_BACKUP_PATH = DATA_DIR / "desks.json"


# ===================================================
# DATABASE CONNECTION
# ===================================================

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Durability guarantees
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

    DESK_BACKUP_PATH.write_text(
        json.dumps(
            [
                {
                    "name": d["name"],
                    "location": d["location"],
                    "is_active": d["is_active"],
                    "admin_only": d["admin_only"],
                }
                for d in desks
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


# ===================================================
# SEED DEFAULT DESKS (SAFE + IDEMPOTENT)
# ===================================================

def seed_desks() -> None:
    default_desks = (
        [
            {"name": f"Desk {i}", "location": "Office", "admin_only": 0}
            for i in range(1, 13)
        ]
        + [
            {"name": f"Desk {i}", "location": "Admin", "admin_only": 1}
            for i in range(13, 16)
        ]
    )

    conn = get_conn()
    c = conn.cursor()

    existing = c.execute("SELECT name FROM desks").fetchall()
    existing_names = {row["name"] for row in existing}

    for desk in _load_desks_backup():
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
    if not DATA_DIR_IS_PERSISTENT and not st.session_state.get(
        "storage_warning_shown", False
    ):
        st.warning(
            "Desk bookings are stored in a local data folder that may not "
            "persist across restarts. Set DESK_BOOKING_DATA_DIR or mount /data "
            "for permanent storage."
        )
        st.session_state["storage_warning_shown"] = True

    init_db()
    seed_desks()
