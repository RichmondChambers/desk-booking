import sqlite3
import os

DB_PATH = "data.db"

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
            can_book INTEGER
        )
    """)

    # ---- ADD is_active COLUMN IF MISSING (SAFE FOR SQLITE) ----
    c.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in c.fetchall()]

    if "is_active" not in columns:
        c.execute(
            "ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1"
        )

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
