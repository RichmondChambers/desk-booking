import streamlit as st
from datetime import datetime, date
from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log

st.set_page_config(
    page_title="Desk Booking",
    layout="wide",
)

# --- Streamlit Cloud Authentication ---
user = st.experimental_user
if not user or not user.is_authenticated:
    st.title("Desk Booking")
    st.write("Please sign in using the Streamlit Cloud login button.")
    st.stop()

# Get user info
email = user.email
name = user.name or email.split("@")[0]

# --- Create DB and ensure user exists ---
init_db()
conn = get_conn()
c = conn.cursor()

row = c.execute(
    "SELECT id, name, role, can_book FROM users WHERE email=?",
    (email,),
).fetchone()

if not row:
    c.execute(
        "INSERT INTO users (name, email, role, can_book) VALUES (?, ?, 'user', 1)",
        (name, email),
    )
    conn.commit()
    row = c.execute(
        "SELECT id, name, role, can_book FROM users WHERE email=?",
        (email,),
    ).fetchone()

conn.close()

# Store user details
st.session_state.user_id = row[0]
st.session_state.user_name = row[1]
st.session_state.role = row[2]
st.session_state.can_book = row[3]
st.session_state.user_email = email

# Sidebar identity
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")

# Enforce no-shows
enforce_no_shows(datetime.now())

# QR code check-in handler
qp = st.query_params
if "checkin" in qp:
    try:
        desk_id = int(qp["checkin"])
        today = date.today().strftime("%Y-%m-%d")
        now_hhmm = datetime.now().strftime("%H:%M")

        conn = get_conn()
        c = conn.cursor()

        booking = c.execute(
            """
            SELECT id, start_time, end_time, checked_in
            FROM bookings
            WHERE user_id=? AND desk_id=? AND date=? AND status='booked'
            """,
            (st.session_state.user_id, desk_id, today),
        ).fetchone()

        if not booking:
            st.warning("No active booking found for this desk today.")
        else:
            booking_id, start_time, end_time, checked_in = booking
            if checked_in:
                st.info("Already checked in.")
            elif start_time <= now_hhmm <= end_time:
                c.execute(
                    "UPDATE bookings SET checked_in=1 WHERE id=?",
                    (booking_id,),
                )
                conn.commit()
                audit_log(
                    st.session_state.user_email,
                    "QR_CHECK_IN",
                    f"booking={booking_id}, desk={desk_id}",
                )
                st.success("Checked in successfully!")
            else:
                st.warning(f"Booking not active. Window: {start_time}–{end_time}")

        conn.close()
    finally:
        st.query_params.clear()
        st.rerun()

# Display instructions
st.title("Desk Booking System")
st.write("Use the sidebar to navigate between functions.")
