from datetime import datetime
from utils.db import get_conn

def audit_log(email, action, details):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO audit_log (email, action, details, timestamp) VALUES (?, ?, ?, ?)",
        (email, action, details, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
