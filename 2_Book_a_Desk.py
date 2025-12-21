import streamlit as st
from datetime import date, datetime
from utils.db import get_conn
from utils.rules import desk_available
from utils.calendar_dwd import create_event
from utils.audit import audit_log

st.title("Book a Desk")

# Block users whose booking rights are suspended
if not st.session_state.get("can_book", 0):
    st.error("Your booking privileges are suspended.")
    st.stop()

booking_date = st.date_input("Date", date.today())

start_time = st.selectbox(
    "Start time",
    [f"{h:02d}:00" for h in range(8, 18)]
)

end_time = st.selectbox(
    "End time",
    [f"{h:02d}:00" for h in range(9, 19)]
)

if start_time >= end_time:
    st.error("End time must be after start time.")
    st.stop()

conn = get_conn()
desks = conn.execute(
    "SELECT id, name, desk_type FROM desks WHERE active=1 ORDER BY id"
).fetchall()
conn.close()

desk = st.selectbox(
    "Desk",
    desks,
    format_func=lambda d: f"{d[1]} ({d[2]})"
)

if st.button("Confirm Booking"):
    desk_id, desk_name, desk_type = desk

    if desk_type == "priority" and st.session_state.role != "admin":
        st.error("Priority desks are restricted.")
        st.stop()

    if not desk_available(
        desk_id,
        str(booking_date),
        start_time,
        end_time
    ):
        st.error("Desk unavailable for selected time range.")
        st.stop()

    created_at = datetime.now().isoformat(timespec="seconds")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO bookings (
            user_id, desk_id, date, start_time,
            end_time, status, created_at, checked_in
        )
        VALUES (?, ?, ?, ?, ?, 'booked', ?, 0)
        """,
        (
            st.session_state.user_id,
            desk_id,
            str(booking_date),
            start_time,
            end_time,
            created_at,
        ),
    )

    booking_id = cur.lastrowid
    conn.commit()

    # Create Google Calendar event (Domain-Wide Delegation)
    event_id = None
    try:
        event_id = create_event(
            user_email=st.session_state.user_email,
            date=str(booking_date),
            start_time=start_time,
            end_time=end_time,
            desk_name=desk_name,
        )
        cur.execute(
            "UPDATE bookings SET calendar_event_id=? WHERE id=?",
            (event_id, booking_id),
        )
        conn.commit()
    except Exception as e:
        audit_log(
            st.session_state.user_email,
            "CALENDAR_CREATE_FAILED",
            f"booking_id={booking_id}, error={repr(e)}",
        )

    conn.close()

    audit_log(
        st.session_state.user_email,
        "BOOKING_CREATED",
        f"booking_id={booking_id}, desk_id={desk_id}, "
        f"date={booking_date}, {start_time}-{end_time}, "
        f"calendar_event_id={event_id}",
    )

    st.success("Booking confirmed and added to your Google Calendar.")
