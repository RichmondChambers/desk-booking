import streamlit as st
from datetime import date
from utils.db import get_conn
from utils.audit import audit_log
from utils.dates import uk_date
from utils.holidays import is_weekend, is_public_holiday


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
# PERMISSION / CONTEXT CHECK
# ---------------------------------------------------
if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

if st.session_state.user_id is None:
    st.error("User session not initialised. Please reload the app.")
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

# UK-format confirmation
st.caption(f"Selected date: {uk_date(date_choice)}")

# Prevent invalid dates
if date_choice < date.today():
    st.error("Bookings cannot be made for past dates.")
    conn.close()
    st.stop()

if is_weekend(date_choice):
    st.error("Bookings cannot be made on weekends.")
    conn.close()
    st.stop()

if is_public_holiday(date_choice):
    st.error("Bookings cannot be made on UK public holidays.")
    conn.close()
    st.stop()

start_time = st.time_input("Start time")
end_time = st.time_input("End time")

if start_time >= end_time:
    st.warning("End time must be after start time.")
    conn.close()
    st.stop()


# ---------------------------------------------------
# DESK AVAILABILITY (ALL DESKS)
# ---------------------------------------------------
def get_booked_desks(conn, date_iso, start, end):
    rows = conn.execute(
        """
        SELECT desk_id
        FROM bookings
        WHERE date = ?
          AND status = 'booked'
          AND (
              (? BETWEEN start_time AND end_time)
              OR
              (? BETWEEN start_time AND end_time)
          )
        """,
        (date_iso, start, end),
    ).fetchall()
    return {row[0] for row in rows}


st.subheader("Desk Availability")

date_iso = date_choice.strftime("%Y-%m-%d")
start_str = start_time.strftime("%H:%M")
end_str = end_time.strftime("%H:%M")

booked_desks = get_booked_desks(conn, date_iso, start_str, end_str)

cols = st.columns(5)  # 15 desks → 3 rows of 5
for desk in range(1, 16):
    with cols[(desk - 1) % 5]:
        if desk in booked_desks:
            st.error(f"Desk {desk}\nUnavailable")
        else:
            st.success(f"Desk {desk}\nAvailable")


# ---------------------------------------------------
# DESK SELECTION
# ---------------------------------------------------
desk_id = st.number_input(
    "Desk number (1–15)",
    min_value=1,
    max_value=15,
    step=1,
)


# ---------------------------------------------------
# CHECK AVAILABILITY (SELECTED DESK)
# ---------------------------------------------------
if st.button("Check Availability"):
    if desk_id in booked_desks:
        st.error("This desk is already booked at that time.")
    else:
        st.success("Desk is available!")


# ---------------------------------------------------
# CONFIRM BOOKING
# ---------------------------------------------------
if st.button("Confirm Booking"):
    if desk_id in booked_desks:
        st.error("This desk is already booked at that time.")
    else:
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
                date_iso,
                start_str,
                end_str,
            ),
        )
        conn.commit()

        audit_log(
            st.session_state.user_email,
            "NEW_BOOKING",
            f"desk={desk_id} {start_str}-{end_str} on {uk_date(date_choice)}",
        )

        st.success("Booking confirmed!")


# ---------------------------------------------------
# CLEANUP
# ---------------------------------------------------
conn.close()
