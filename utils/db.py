import json
import os
import sqlite3
from pathlib import Path

import streamlit as st

DB_FILENAME = "desk-booking.db"
DESK_BACKUP_FILENAME = "desks.json"


# ===================================================
# DATA DIRECTORY RESOLUTION
# ===================================================

def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return True
    except OSError:
        return False


def _resolve_data_dir() -> tuple[Path, bool]:
    """
    Resolve a persistent directory for data storage.

    Priority order:
    1) DESK_BOOKING_DB_PATH (parent directory)
    2) DESK_BOOKING_DATA_DIR
    3) /data (Streamlit Cloud)
    4) ./data (only if DESK_BOOKING_ALLOW_EPHEMERAL=1)
    """

    db_path_env = os.getenv("DESK_BOOKING_DB_PATH")
    allow_ephemeral = os.getenv("DESK_BOOKING_ALLOW_EPHEMERAL") == "1"

    if db_path_env:
        db_path = Path(db_path_env).expanduser()
        if _is_writable_dir(db_path.parent):
            return db_path.parent, True
        raise RuntimeError(
            "DESK_BOOKING_DB_PATH points to an unwritable directory."
        )

    data_dir_env = os.getenv("DESK_BOOKING_DATA_DIR")
    if data_dir_env:
        data_dir = Path(data_dir_env).expanduser()
        if _is_writable_dir(data_dir):
            return data_dir, True
        raise RuntimeError(
            "DESK_BOOKING_DATA_DIR is not writable."
        )

    persistent_candidates = [Path("/data")]
    for candidate in persistent_candidates:
        if _is_writable_dir(candidate):
            return candidate, True

    if allow_ephemeral:
        project_data = Path(__file__).resolve().parent.parent / "data"
        if _is_writable_dir(project_data):
            return project_data, False

    raise RuntimeError(
        "No writable persistent data directory available. "
        "Set DESK_BOOKING_DATA_DIR or DESK_BOOKING_DB_PATH to prevent booking loss."
    )


# ===================================================
# PATH RESOLUTION
# ===================================================

DATA_DIR, DATA_DIR_IS_PERSISTENT = _resolve_data_dir()

_db_path_env = os.getenv("DESK_BOOKING_DB_PATH")
if _db_path_env:
    DB_PATH = Path(_db_path_env).expanduser()
else:
    DB_PATH = DATA_DIR / DB_FILENAME

DESK_BACKUP_PATH = DATA_DIR / DESK_BACKUP_FILENAME


# ===================================================
# DATABASE CONNECTION
# ===================================================

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")

    return conn


# ===================================================
# DATABASE INITIALIZATION
# ===================================================

def init_db() -> None:
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
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

    cursor.execute(
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

    cursor.execute(
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

    cursor.execute(
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
                    "name": desk["name"],
                    "location": desk["location"],
                    "is_active": desk["is_active"],
                    "admin_only": desk["admin_only"],
                }
                for desk in desks
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


# ===================================================
# SEED DEFAULT DESKS
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
    cursor = conn.cursor()

    existing = cursor.execute("SELECT name FROM desks").fetchall()
    existing_names = {row["name"] for row in existing}

    for desk in _load_desks_backup():
        if desk["name"] not in existing_names:
            cursor.execute(
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
            cursor.execute(
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
            "persist across restarts. Set DESK_BOOKING_DATA_DIR or "
            "DESK_BOOKING_DB_PATH for permanent storage."
        )
        st.session_state["storage_warning_shown"] = True

    init_db()
    seed_desks()
