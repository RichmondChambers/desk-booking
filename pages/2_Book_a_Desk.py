import streamlit as st
from datetime import datetime
from utils.db import get_conn
from utils.audit import audit_log
from utils.dates import uk_date


# ---------------------------------------------------
# PAGE SETUP
# ---------------------------------------------------
st.title("Book a Desk")


# ---------------------------------------------------
# SESSION STATE SAFETY (CRITICAL)
# ---------------------------------------------------
st.session_state.setdefault("can_book", 1)
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", "internal.user@richmondchambers.com")


# ---------------------------------------------------
# PERMISSION CHECK
# ---------------------------------------------------
if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()


# ---------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------
conn = get_conn()
c = conn.cursor()


# ---------------------------------------------------
# USER INPUTS
# ---------------------------------------------------
date_choice = st.date_input("Select date")
st.caption(f"Selected date: {uk_date(date_choice)}")

start_time = st.time_input("Start time")
end_time = st.time_input("End time")

if start_time >= end_time:
    st.warning("End time must be after start time.")
    conn.close()
    st.stop()

desk_id = st.number_input(
    "Desk number (1–15)",
    min_value=1,
    max_value=15,
    step=1,
)


# ---------------------------------------------------
# CHECK AVAILABILITY
# ---------------------------------------------------
if st.button("Check Availability"):
    conflicts = c.execute(
        """
        SELECT 1
        FROM bookings
        WHERE desk_id=? AND date=? AND status='booked'
        AND (
            (? BETWEEN start_time AND end_time)
            OR
            (? BETWEEN start_time AND end_time)
        )
        """,
        (
            desk_id,
            date_choice.strftime("%Y-%m-%d"),
            start_time.strftime("%H:%M"),
            end_time.strftime("%H:%M"),
        ),
    ).fetchall()

    if conflicts:
        st.error("This desk is already booked at that time.")
    else:
        st.success("Desk is available!")


# ---------------------------------------------------
# CONFIRM BOOKING
# ---------------------------------------------------
if st.button("Confirm Booking"):
    c.execute(
        """
        INSERT INTO bookings
            (user_id, desk_id, date, start_time, end_time, status)
        VALUES
            (?, ?, ?, ?, ?, 'booked')
        """,
        (
            st.session_state.user_id,
            desk_id,
            date_choice.strftime("%Y-%m-%d"),
            start_time.strftime("%H:%M"),
            end_time.strftime("%H:%M"),
        ),
    )
    conn.commit()

    audit_log(
        st.session_state.user_email,
        "NEW_BOOKING",
        f"desk={desk_id} {start_time}-{end_time} on {uk_date(date_choice)}",
    )

    st.success("Booking confirmed!")


# ---------------------------------------------------
# CLEANUP
# ---------------------------------------------------
conn.close()
