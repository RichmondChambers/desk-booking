import streamlit as st
st.write("DEBUG session_state:", dict(st.session_state))
from datetime import datetime, date
from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log

st.set_page_config(
    page_title="Desk Booking",
    layout="centered",
    initial_sidebar_state="collapsed"
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
    unsafe_allow_html=True
)

# Initialise database
init_db()

# Always process OAuth callback first
handle_oauth_response()

# --- Authentication handling (must run first) ---
handle_oauth_response()

if "user_id" not in st.session_state:
    st.title("Desk Booking")
    st.write("Please sign in with your Google Workspace account.")
    google_login_link()
    st.stop()

# Enforce no-shows on each load
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
            (st.session_state.user_id, desk_id, today)
        ).fetchone()

        if not booking:
            st.warning("No active booking found for this desk today.")
        else:
            booking_id, start_time, end_time, checked_in = booking
            if checked_in:
                st.info("You are already checked in.")
            elif start_time <= now_hhmm <= end_time:
                c.execute(
                    "UPDATE bookings SET checked_in=1 WHERE id=?",
                    (booking_id,)
                )
                conn.commit()
                audit_log(
                    st.session_state.user_email,
                    "CHECK_IN_QR",
                    f"booking_id={booking_id}, desk_id={desk_id}"
                )
                st.success("Checked in successfully.")
            else:
                st.warning(
                    f"Booking not active. Booking window: {start_time}–{end_time}"
                )
        conn.close()
    finally:
        st.query_params.clear()

# Sidebar
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")
