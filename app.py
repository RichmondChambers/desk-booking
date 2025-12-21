import streamlit as st
from datetime import datetime, date

from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log


# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------
st.set_page_config(page_title="Desk Booking", layout="wide")


# ---------------------------------------------------
# USER IDENTITY (AUTH REMOVED)
# ---------------------------------------------------
# Replace Google / Streamlit Cloud authentication with
# a simple internal placeholder user

email = "internal.user@richmondchambers.com"
name = "Internal User"


# ---------------------------------------------------
# DATABASE USER HANDLING
# ---------------------------------------------------
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


# ---------------------------------------------------
# SAVE USER IN SESSION
# ---------------------------------------------------
st.session_state.user_id = row[0]
st.session_state.user_name = row[1]
st.session_state.role = row[2]
st.session_state.can_book = row[3]
st.session_state.user_email = email


# ---------------------------------------------------
# SIDEBAR USER INFO
# ---------------------------------------------------
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Email:** {email}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")


# ---------------------------------------------------
# ENFORCE NO-SHOWS
# ---------------------------------------------------
enforce_no_shows(datetime.now())


# ---------------------------------------------------
# QR CHECK-IN HANDLER
# ---------------------------------------------------
params = st.query_params

if "checkin" in params:
    try:
        desk_id = int(params["checkin"])
        today = date.today().strftime("%Y-%m-%d")
        now_time = datetime.now().strftime("%H:%M")

        conn = get_conn()
        c = conn.cursor()

        booking = c.execute("""
            SELECT id, start_time, end_time, checked_in
            FROM bookings
            WHERE user_id=? AND desk_id=? AND date=? AND status='booked'
        """, (st.session_state.user_id, desk_id, today)).fetchone()

        if not booking:
            st.warning("No active booking found for this desk today.")
        else:
            booking_id, start_t, end_t, checked_in = booking

            if checked_in:
                st.info("Already checked in.")
            elif start_t <= now_time <= end_t:
                c.execute(
                    "UPDATE bookings SET checked_in=1 WHERE id=?",
                    (booking_id,),
                )
                conn.commit()

                audit_log(
                    email,
                    "QR_CHECK_IN",
                    f"booking={booking_id}, desk={desk_id}",
                )
                st.success("Checked in successfully.")
            else:
                st.warning(f"Booking only valid between {start_t}–{end_t}.")

        conn.close()

    finally:
        st.query_params.clear()
        st.rerun()


# ---------------------------------------------------
# MAIN PAGE
# ---------------------------------------------------
st.title("Desk Booking System")
st.write("Use the sidebar to navigate between system functions.")
