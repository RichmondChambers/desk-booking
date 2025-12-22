import sqlite3

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
