from utils.db import get_conn
import streamlit as st
from datetime import datetime

def log_action(action, details):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO audit_log (email, action, details, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (
            st.session_state.user_email,
            action,
            details,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
