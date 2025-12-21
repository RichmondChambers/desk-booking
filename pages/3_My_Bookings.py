import streamlit as st
from datetime import datetime
from utils.db import get_conn
from utils.audit import audit_log

st.title("My Bookings")

conn = get_conn()
c = conn.cursor()

rows = c.execute("""
    SELECT id, desk_id, date, start_time, end_time, status, checked_in
    FROM bookings
    WHERE user_id=?
    ORDER BY date DESC, start_time DESC
""", (st.session_state.user_id,)).fetchall()

if not rows:
    st.info("No bookings found.")
    st.stop()

for booking_id, desk, date_, start, end, status, checked_in in rows:
    st.markdown(
        f"""
        ### Desk {desk} — {date_}
        **Time:** {start}–{end}  
        **Status:** {status}  
        **Checked In:** {"Yes" if checked_in else "No"}  
        """
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Cancel {booking_id}", key=f"cancel_{booking_id}"):
            c.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
            conn.commit()
            audit_log(st.session_state.user_email, "CANCEL_BOOKING", f"id={booking_id}")
            st.success("Booking cancelled.")
            st.rerun()

conn.close()
