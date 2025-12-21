import streamlit as st
import pandas as pd
from utils.db import get_conn

if st.session_state.role != "admin":
    st.error("Admin access only.")
    st.stop()

st.title("HR Compliance Reporting")

conn = get_conn()

st.subheader("Attendance vs Bookings")

attendance = pd.read_sql(
    """
    SELECT u.name, u.email,
           COUNT(*) AS total_bookings,
           SUM(CASE WHEN b.checked_in=1 THEN 1 ELSE 0 END) AS attended,
           SUM(CASE WHEN b.status='no-show' THEN 1 ELSE 0 END) AS no_shows
    FROM bookings b
    JOIN users u ON u.id=b.user_id
    GROUP BY u.id
    ORDER BY no_shows DESC, total_bookings DESC
    """,
    conn,
)

st.dataframe(attendance, use_container_width=True)

st.subheader("No-show Details")

noshow = pd.read_sql(
    """
    SELECT b.id, u.name, u.email, d.name AS desk,
           b.date, b.start_time, b.end_time, b.created_at
    FROM bookings b
    JOIN users u ON u.id=b.user_id
    JOIN desks d ON d.id=b.desk_id
    WHERE b.status='no-show'
    ORDER BY b.date DESC, b.start_time ASC
    """,
    conn,
)

st.dataframe(noshow, use_container_width=True)

st.subheader("Audit Log (latest 500)")

audit = pd.read_sql(
    """
    SELECT timestamp, actor_email, action, details
    FROM audit_log
    ORDER BY timestamp DESC
    LIMIT 500
    """,
    conn,
)

st.dataframe(audit, use_container_width=True)

conn.close()

st.divider()
st.subheader("Export CSVs")

col1, col2, col3 = st.columns(3)

with col1:
    st.download_button(
        "Attendance CSV",
        attendance.to_csv(index=False),
        "attendance.csv",
        "text/csv",
    )

with col2:
    st.download_button(
        "No-shows CSV",
        noshow.to_csv(index=False),
        "no_shows.csv",
        "text/csv",
    )

with col3:
    st.download_button(
        "Audit Log CSV",
        audit.to_csv(index=False),
        "audit_log.csv",
        "text/csv",
    )
