import streamlit as st
import pandas as pd
from utils.db import get_conn
from utils.calendar_dwd import delete_event
from utils.audit import audit_log

if st.session_state.role != "admin":
    st.error("Admin access only.")
    st.stop()

st.title("Admin Panel")

conn = get_conn()

st.subheader("All Bookings")

df = pd.read_sql(
    """
    SELECT b.id, u.name AS user_name, u.email, d.name AS desk,
           b.date, b.start_time, b.end_time,
           b.status, b.checked_in
    FROM bookings b
    JOIN users u ON u.id=b.user_id
    JOIN desks d ON d.id=b.desk_id
    ORDER BY b.date DESC, b.start_time ASC
    """,
    conn,
)

st.dataframe(df, use_container_width=True)

st.divider()
st.subheader("Force cancel booking")

booking_id = st.number_input("Booking ID", step=1)

if st.button("Cancel Booking"):
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT u.email, b.calendar_event_id
        FROM bookings b
        JOIN users u ON u.id=b.user_id
        WHERE b.id=? AND b.status='booked'
        """,
        (booking_id,),
    ).fetchone()

    if not row:
        st.error("Booking not found or already cancelled.")
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
                "CALENDAR_DELETE_FAILED_ADMIN",
                f"booking_id={booking_id}, error={repr(e)}",
            )

        audit_log(
            st.session_state.user_email,
            "ADMIN_CANCEL_BOOKING",
            f"booking_id={booking_id}, affected_user={user_email}",
        )
        st.success("Booking cancelled and calendar updated.")

st.divider()
st.subheader("Users")

users = pd.read_sql(
    "SELECT id, name, email, role, can_book FROM users ORDER BY id",
    conn,
)

st.dataframe(users, use_container_width=True)

user_id = st.number_input("User ID", step=1, key="uid")

col1, col2 = st.columns(2)

with col1:
    if st.button("Suspend booking rights"):
        conn.execute("UPDATE users SET can_book=0 WHERE id=?", (user_id,))
        conn.commit()
        audit_log(
            st.session_state.user_email,
            "SUSPEND_USER",
            f"user_id={user_id}",
        )
        st.success("User suspended.")

with col2:
    if st.button("Reinstate booking rights"):
        conn.execute("UPDATE users SET can_book=1 WHERE id=?", (user_id,))
        conn.commit()
        audit_log(
            st.session_state.user_email,
            "REINSTATE_USER",
            f"user_id={user_id}",
        )
        st.success("User reinstated.")

conn.close()
