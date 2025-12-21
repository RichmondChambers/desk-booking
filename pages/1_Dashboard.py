import streamlit as st
from datetime import datetime
from utils.db import get_conn

st.title("Dashboard")

# --- User Details ---
st.subheader("Your Profile")
st.write(f"**Name:** {st.session_state.user_name}")
st.write(f"**Email:** {st.session_state.user_email}")
st.write(f"**Role:** {st.session_state.role}")

# --- Booking Summary ---
st.subheader("Today's Bookings")

conn = get_conn()
c = conn.cursor()

rows = c.execute("""
    SELECT desk_id, start_time, end_time, status, checked_in
    FROM bookings
    WHERE user_id=? AND date=?
    ORDER BY start_time
""", (st.session_state.user_id, datetime.today().strftime("%Y-%m-%d"))).fetchall()

conn.close()

if not rows:
    st.info("You have no bookings for today.")
else:
    for desk, start, end, status, checked_in in rows:
        st.markdown(
            f"""
            • **Desk {desk}**  
            • Time: **{start}–{end}**  
            • Status: **{status}**  
            • Checked in: **{"Yes" if checked_in else "No"}**
            """
        )

st.write("---")
st.write("Use the sidebar to navigate to booking features.")
