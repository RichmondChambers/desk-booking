import streamlit as st
from datetime import datetime, date
from utils.db import get_conn
from utils.audit import audit_log
from utils.qr import generate_qr


st.title("My Bookings")

user_id = st.session_state.user_id
today_str = date.today().strftime("%Y-%m-%d")

conn = get_conn()
c = conn.cursor()

# ============================================================
# FETCH UPCOMING BOOKINGS
# ============================================================

upcoming = c.execute("""
    SELECT id, desk_id, date, start_time, end_time, status, checked_in
    FROM bookings
    WHERE user_id=?
      AND date >= ?
    ORDER BY date, start_time
""", (user_id, today_str)).fetchall()


# ============================================================
# FETCH PAST BOOKINGS
# ============================================================

past = c.execute("""
    SELECT id, desk_id, date, start_time, end_time, status, checked_in
    FROM bookings
    WHERE user_id=?
      AND date < ?
    ORDER BY date DESC, start_time DESC
""", (user_id, today_str)).fetchall()

conn.close()


# ============================================================
# SHOW UPCOMING BOOKINGS
# ============================================================

st.subheader("Upcoming Bookings")

if not upcoming:
    st.info("You have no upcoming bookings.")
else:
    for booking in upcoming:

        booking_id, desk_id, b_date, start, end, status, checked_in = booking

        with st.container():
            st.markdown(
                f"""
                **Desk {desk_id}**  
                • Date: **{b_date}**  
                • Time: **{start}–{end}**  
                • Status: **{status}**  
                • Checked in: **{'Yes' if checked_in else 'No'}**
                """
            )

            # ---- QR CODE ---------
            qr_url = st.secrets["oauth"]["app_url"] + f"?checkin={desk_id}"
            qr_img = generate_qr(qr_url)

            st.image(qr_img, caption=f"QR Code for Desk {desk_id}", width=180)

            # ---- CANCEL BOOKING BUTTON ----
            cancel_key = f"cancel_{booking_id}"
            if st.button("Cancel Booking", key=cancel_key):
                conn = get_conn()
                c = conn.cursor()

                c.execute("""
                    UPDATE bookings
                    SET status='cancelled'
                    WHERE id=? AND user_id=?
                """, (booking_id, user_id))

                conn.commit()
                conn.close()

                audit_log(
                    st.session_state.user_email,
                    "BOOKING_CANCELLED",
                    f"booking_id={booking_id}, desk={desk_id}"
                )

                st.success("Booking cancelled.")
                st.rerun()

            st.write("---")

# ============================================================
# SHOW PAST BOOKINGS
# ============================================================

st.subheader("Past Bookings")

if not past:
    st.info("You have no past bookings.")
else:
    for booking in past:

        booking_id, desk_id, b_date, start, end, status, checked_in = booking

        st.markdown(
            f"""
            **Desk {desk_id}**  
            • Date: **{b_date}**  
            • Time: **{start}–{end}**  
            • Status: **{status}**  
            • Checked in: **{'Yes' if checked_in else 'No'}**
            """
        )
        st.write("---")
