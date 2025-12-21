import streamlit as st
import pandas as pd
from datetime import date
from utils.db import get_conn
from utils.calendar_dwd import delete_event
from utils.audit import audit_log

st.title("My Bookings")

conn = get_conn()
df = pd.read_sql(
    """
    SELECT b.id, d.name AS desk, b.date, b.start_time,
           b.end_time, b.status, b.checked_in
    FROM bookings b
    JOIN desks d ON d.id=b.desk_id
    WHERE b.user_id=?
    ORDER BY b.date DESC, b.start_time ASC
    """,
    conn,
    params=(st.session_state.user_id,),
)
conn.close()

st.dataframe(df, use_container_width=True)

booking_id = st.number_input("Booking ID", step=1)

col1, col2 = st.columns(2)

with col1:
    if st.button("Check In (manual)"):
        today = date.today().strftime("%Y-%m-%d")
        conn = get_conn()
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT id FROM bookings
            WHERE id=? AND user_id=? AND date=? AND status='booked'
            """,
            (booking_id, st.session_state.user_id, today),
        ).fetchone()

        if not row:
            st.error("No active booking found for today with that ID.")
        else:
            cur.execute(
                "UPDATE bookings SET checked_in=1 WHERE id=?",
                (booking_id,),
            )
            conn.commit()
            audit_log(
                st.session_state.user_email,
                "CHECK_IN_MANUAL",
                f"booking_id={booking_id}",
            )
            st.success("Checked in.")
        conn.close()

with col2:
    if st.button("Cancel Booking"):
        conn = get_conn()
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT u.email, b.calendar_event_id
            FROM bookings b
            JOIN users u ON u.id=b.user_id
            WHERE b.id=? AND b.user_id=? AND b.status='booked'
            """,
            (booking_id, st.session_state.user_id),
        ).fetchone()

        if not row:
            st.error("Booking not found or already cancelled.")
            conn.close()
        else:
            user_email, event_id = row
            cur.execute(
                "UPDATE bookings SET status='cancelled' WHERE id=?",
                (booking_id,),
            )
            conn.commit()

            try:
                delete_event(user_email=user_email, event_id=event_id)
            except Exception as e:
                audit_log(
                    st.session_state.user_email,
                    "CALENDAR_DELETE_FAILED",
                    f"booking_id={booking_id}, error={repr(e)}",
                )

            audit_log(
                st.session_state.user_email,
                "BOOKING_CANCELLED",
                f"booking_id={booking_id}, calendar_event_id={event_id}",
            )
            conn.close()
            st.success("Cancelled and removed from Google Calendar.")
