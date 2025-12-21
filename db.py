import os
import sqlite3

DB_PATH = os.environ.get("DESKBOOK_DB_PATH", "data/desk_booking.db")

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        can_book INTEGER NOT NULL DEFAULT 1
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS desks (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        desk_type TEXT NOT NULL DEFAULT 'standard',
        active INTEGER NOT NULL DEFAULT 1
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        desk_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        checked_in INTEGER NOT NULL DEFAULT 0,
        calendar_event_id TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(desk_id) REFERENCES desks(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        actor_email TEXT NOT NULL,
        action TEXT NOT NULL,
        details TEXT NOT NULL
    )
    """)

    # Seed desks (15 desks, desks 1–2 are priority)
    if c.execute("SELECT COUNT(*) FROM desks").fetchone()[0] == 0:
        for i in range(1, 16):
            desk_type = "priority" if i in (1, 2) else "standard"
            c.execute(
                "INSERT INTO desks (id, name, desk_type, active) VALUES (?, ?, ?, ?)",
                (i, f"Desk {i}", desk_type, 1)
            )

    # Seed initial admin user (change email later)
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        c.execute(
            "INSERT INTO users (name, email, role, can_book) VALUES (?, ?, ?, ?)",
            ("Admin", "admin@yourdomain.com", "admin", 1)
        )

    conn.commit()
    conn.close()
