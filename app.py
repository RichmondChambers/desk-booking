import streamlit as st
from datetime import datetime, date

from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log
from utils.google_auth import google_login_link, handle_oauth_response

st.set_page_config(
    page_title="Desk Booking",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Mobile-friendly CSS
st.markdown(
    """
    <style>
    button, [role="button"] {
        width: 100%;
        font-size: 1.05rem;
    }
    input, select, textarea {
        font-size: 1.05rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---- HANDLE GOOGLE OAUTH CALLBACK ----
handle_oauth_response()

# If user not logged in, show login screen
if "user_email" not in st.session_state:
    st.title("Desk Booking")
    st.write("Please sign in with your Google Workspace account.")
    google_login_link()
    st.stop()

# ---- USER IS AUTHENTICATED ----
email = st.session_state.user_email
name = st.session_state.user_name or email.split("@")[0]

# Initialise database
init_db()

# Ensure user exists in DB
conn = get_conn()
cur = conn.cursor()

row = cur.execute(
    "SELECT id, name, role, can_book FROM users WHERE email=?",
    (email,),
).fetchone()

if not row:
    cur.execute(
        "INSERT INTO users (name, email, role, can_book) VALUES (?, ?, 'user', 1)",
        (name, email),
    )
    conn.commit()
    row = cur.execute(
        "SELECT id, name, role, can_book FROM users WHERE email=?",
        (email,),
    ).fetchone()

conn.close()

# Store user details in session_state
st.session_state.update(
    {
        "user_id": row[0],
        "user_name": row[1],
        "role": row[2],
        "can_book": row[3],
        "user_email": email,
    }
)

# Sidebar identity
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")

# Enforce no-shows on each load
enforce_no_shows(datetime.now())

# ---- QR CHECK-IN HANDLING ----
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
                st.info("You are already checked in.")
            elif start_time <= now_hhmm <= end_time:
                c.execute("UPDATE bookings SET checked_in=1 WHERE id=?", (booking_id,))
                conn.commit()
                audit_log(
                    st.session_state.user_email,
                    "CHECK_IN_QR",
                    f"booking_id={booking_id}, desk_id={desk_id}",
                )
                st.success("Checked in successfully.")
            else:
                st.warning(
                    f"Booking not active. Booking window: {start_time}–{end_time}"
                )

        conn.close()
    finally:
        st.query_params.clear()
        st.rerun()
