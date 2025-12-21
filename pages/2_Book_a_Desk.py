import streamlit as st
from datetime import datetime, timedelta
from utils.db import get_conn
from utils.audit import audit_log
from utils.qr import generate_qr

st.title("Book a Desk")

if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

conn = get_conn()
c = conn.cursor()

# User inputs
date_choice = st.date_input("Select date")
start_time = st.time_input("Start time")
end_time = st.time_input("End time")

if start_time >= end_time:
    st.warning("End time must be after start time.")
    st.stop()

# Desk selection
desk_id = st.number_input("Desk number (1–15)", min_value=1, max_value=15, step=1)

# Check conflicts
if st.button("Check Availability"):
    conflicts = c.execute("""
        SELECT * FROM bookings
        WHERE desk_id=? AND date=? AND (
            (? BETWEEN start_time AND end_time)
            OR
            (? BETWEEN start_time AND end_time)
        ) AND status='booked'
    """, (desk_id, date_choice.strftime("%Y-%m-%d"),
          start_time.strftime("%H:%M"), end_time.strftime("%H:%M"))).fetchall()

    if conflicts:
        st.error("This desk is already booked at that time.")
    else:
        st.success("Desk is available!")

# Book it
if st.button("Confirm Booking"):
    c.execute("""
        INSERT INTO bookings (user_id, desk_id, date, start_time, end_time, status)
        VALUES (?, ?, ?, ?, ?, 'booked')
    """, (
        st.session_state.user_id,
        desk_id,
        date_choice.strftime("%Y-%m-%d"),
        start_time.strftime("%H:%M"),
        end_time.strftime("%H:%M"),
    ))
    conn.commit()

    audit_log(
        st.session_state.user_email,
        "NEW_BOOKING",
        f"desk={desk_id} {start_time}-{end_time} on {date_choice}",
    )

    st.success("Booking confirmed!")

    # Generate QR code
    qr_url = st.secrets["app_url"] + f"?checkin={desk_id}"
    qr_img = generate_qr(qr_url)
    st.image(qr_img, caption="Scan to Check In")

conn.close()
