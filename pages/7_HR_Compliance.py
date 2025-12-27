import streamlit as st
import pandas as pd
from utils.auth import require_admin
from utils.db import ensure_db, get_conn
from utils.styles import apply_lato_font

apply_lato_font()
st.title("HR Compliance Reporting")
ensure_db()
require_admin()

conn = get_conn()
c = conn.cursor()

# No-show report
st.subheader("No-show Records")
nos = c.execute("""
    SELECT b.id, u.name, u.email, b.date, b.start_time, b.end_time
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE b.status='no_show'
    ORDER BY date DESC
""").fetchall()

df_nos = pd.DataFrame(
    nos,
    columns=["Booking ID", "User", "Email", "Date", "Start", "End"],
)
st.dataframe(df_nos)

# Attendance summary
st.subheader("Attendance Summary")
attendance = c.execute("""
    SELECT u.name, u.email,
        SUM(CASE WHEN b.checked_in=1 THEN 1 ELSE 0 END) AS attended,
        SUM(CASE WHEN b.status='no_show' THEN 1 ELSE 0 END) AS no_shows
    FROM users u
    LEFT JOIN bookings b ON b.user_id = u.id
    GROUP BY u.id
""").fetchall()

df_att = pd.DataFrame(
    attendance,
    columns=["User", "Email", "Attended", "No Shows"],
)
st.dataframe(df_att)

conn.close()
