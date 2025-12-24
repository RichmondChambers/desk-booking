import streamlit as st
from datetime import date
from utils.db import get_conn
from utils.audit import log_action
from utils.dates import uk_date

# ---------------------------------------------------
# PAGE SETUP
# ---------------------------------------------------
st.title("My Bookings")

# ---------------------------------------------------
# SESSION STATE SAFETY
# ---------------------------------------------------
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", "internal.user@richmondchambers.com")

# ---------------------------------------------------
# VALIDATE USER CONTEXT
# ---------------------------------------------------
if st.session_state.user_id is None:
    st.error("User session not initialised. Please reload the app.")
    st.stop()

user_id = st.session_state.user_id
today_str = date.today().strftime("%Y-%m-%d")

# ---------------------------------------------------
# DB HELPER
# ---------------------------------------------------
def run_db(query, params=()):
    conn = get_conn()
    conn.execute(query, params)
    conn.commit()
    conn.close()

# ---------------------------------------------------
# FETCH BOOKINGS
# ---------------------------------------------------
conn = get_conn()

upcoming = conn.execute(
    """
    SELECT id, desk_id, date, start_time, end_time, status, checked_in
    FROM bookings
    WHERE user_id = ?
      AND date >= ?
      AND status = 'booked'
    ORDER BY date, start_time
    """,
    (user_id, today_str),
).fetchall()

past = conn.execute(
    """
    SELECT id, desk_id, date, start_time, end_time, status, checked_in
    FROM bookings
    WHERE user_id = ?
      AND date < ?
      AND status IN ('booked', 'cancelled')
    ORDER BY date DESC, start_time DESC
    """,
    (user_id, today_str),
).fetchall()

conn.close()

# ---------------------------------------------------
# SHOW UPCOMING BOOKINGS
# ---------------------------------------------------
st.subheader("Upcoming Bookings")

if not upcoming:
    st.info("You have no upcoming bookings.")
else:
    for booking_id, desk_id, b_date, start, end, status, checked_in in upcoming:
        with st.container():
            st.markdown(
                f"""
                **Desk {desk_id}**  
                • Date: **{uk_date(b_date)}**  
                • Time: **{start}–{end}**  
                • Status: **{status}**  
                • Checked in: **{'Yes' if checked_in else 'No'}**
                """
            )

            if st.button("Cancel Booking", key=f"cancel_{booking_id}"):
                run_db(
                    """
                    UPDATE bookings
                    SET status='cancelled'
                    WHERE id=? AND user_id=? AND status='booked'
                    """,
                    (booking_id, user_id),
                )

                log_action(
                    "BOOKING_CANCELLED",
                    f"booking_id={booking_id}, desk_id={desk_id}",
                )

                st.success("Booking cancelled.")
                st.rerun()

            st.divider()

# ---------------------------------------------------
# SHOW PAST BOOKINGS
# ---------------------------------------------------
st.subheader("Past Bookings")

if not past:
    st.info("You have no past bookings.")
else:
    for booking_id, desk_id, b_date, start, end, status, checked_in in past:
        st.markdown(
            f"""
            **Desk {desk_id}**  
            • Date: **{uk_date(b_date)}**  
            • Time: **{start}–{end}**  
            • Status: **{status}**  
            • Checked in: **{'Yes' if checked_in else 'No'}**
            """
        )
        st.divider()
