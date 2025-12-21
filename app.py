import streamlit as st
from datetime import datetime, date

from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log

# -------------------------------
# Streamlit App Configuration
# -------------------------------
st.set_page_config(
    page_title="Desk Booking",
    layout="wide",
)

# -------------------------------
# Streamlit Cloud Authentication
# -------------------------------
user = st.experimental_user

if user is None:
    # This produces a login screen identical to your screenshot.
    st.title("Richmond Chambers – Internal Tool")
    st.write("Please sign in with a Richmond Chambers Google Workspace account to access this app.")
    st.stop()

# After login (user is now authenticated)
email = user.email
name = user.name or email.split("@")[0]

# -------------------------------
# Database Setup & Ensure User Exists
# -------------------------------
init_db()
conn = get_conn()
c = conn.cursor()

row = c.execute(
    "SELECT id, name, role, can_book FROM users WHERE email=?",
    (email,),
).fetchone()

if not row:
    # New user — add with default "user" role and booking permission enabled
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

# -------------------------------
# Store User in Session State
# -------------------------------
st.session_state.user_id = row[0]
st.session_state.user_name = row[1]
st.session_state.role = row[2]
st.session_state.can_book = row[3]
st.session_state.user_email = email

# -------------------------------
# Sidebar Identity
# -------------------------------
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")

# -------------------------------
# Enforce No-Show Rules
# -------------------------------
enforce_no_shows(datetime.now())

# -------------------------------
# QR Code Check-In Handler
# -------------------------------
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
                # Mark as checked in
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
                st.warning(
                    f"Booking not active. Only valid during {start_time}–{end_time}."
                )

        conn.close()

    finally:
        st.query_params.clear()
        st.rerun()

# -------------------------------
# Main Page Content
# -------------------------------
st.title("Desk Booking System")
st.write("Use the sidebar to navigate between functions.")
