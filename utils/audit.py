from datetime import datetime
from utils.db import get_conn

def audit_log(actor_email: str, action: str, details: str) -> None:
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO audit_log (timestamp, actor_email, action, details)
        VALUES (?, ?, ?, ?)
        """,
        (datetime.now().isoformat(timespec="seconds"), actor_email, action, details)
    )
    conn.commit()
    conn.close()
