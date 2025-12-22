import streamlit as st
from datetime import datetime, date
from utils.db import get_conn
from utils.audit import audit_log


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

if st.session_state.user_id is None:
    st.error("User session not initialised. Please reload the app.")
    st.stop()


# ---------------------------------------------------
# DATE PARSING (UK FORMAT)
# ---------------------------------------------------
def parse_uk_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except Exception:
        return None


# ---------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------
conn = get_conn()
c = conn.cursor()


# ---------------------------------------------------
# USER INPUTS
# ---------------------------------------------------
default_uk_date = date.today().strftime("%d/%m/%Y")

date_str = st.text_input(
    "Select date (DD/MM/YYYY)",
    value=default_uk_date,
    help="Enter the date in UK format, e.g. 25/12/2025",
)

date_choice = parse_uk_date(date_str)

if date_choice is None:
    st.error("Please enter a valid date in DD/MM/YYYY format.")
    conn.close()
    st.stop()

if date_choice < date.today():
    st.error("Bookings cannot be made for past dates.")
    conn.close()
    st.stop()

st.caption(f"Selected date: {date_choice.strftime('%d/%m/%Y')}")

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
        WHERE desk_id = ?
          AND date = ?
          AND status = 'booked'
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
        f"desk={desk_id} {start_time}-{end_time} on {date_choice.strftime('%d/%m/%Y')}",
    )

    st.success("Booking confirmed!")


# ---------------------------------------------------
# CLEANUP
# ---------------------------------------------------
conn.close()
