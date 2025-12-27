import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(
    os.getenv(
        "DESK_BOOKING_DB_PATH",
        BASE_DIR / "data" / "data.db",
    )
).expanduser()

DB_PATH.parent.mkdir(parents=True, exist_ok=True)





+26
-2

import os
import sqlite3
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "data.db"

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

DB_PATH = Path(
    os.getenv(
        "DESK_BOOKING_DB_PATH",
        _secret_db_path() or DEFAULT_DB_PATH,
    )
).expanduser()

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

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
    # BOOKINGS TABLE
    # ---------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            desk_id INTEGER,
            date TEXT,
            start_time TEXT,
            end_time TEXT,
            status TEXT,
            checked_in INTEGER DEFAULT 0
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

def seed_desks():
    """
    Insert default desks if none exist.
    Safe to run multiple times.
    """
    conn = get_conn()
    c = conn.cursor()

    count = c.execute("SELECT COUNT(*) FROM desks").fetchone()[0]

    if count == 0:
        c.executemany(
            "INSERT INTO desks (name, location) VALUES (?, ?)",
            [
                ("Desk 1", "Office"),
                ("Desk 2", "Office"),
                ("Desk 3", "Office"),
            ]
        )
        conn.commit()

    conn.close()

def make_admin(email: str):
    """
    Promote a user to admin and ensure they can book.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET role = 'admin', can_book = 1 WHERE email = ?",
        (email,),
    )
    conn.commit()
    conn.close()
