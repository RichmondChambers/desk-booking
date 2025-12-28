import streamlit as st
from datetime import date
from utils.db import ensure_db
from utils.audit import log_action
from utils.dates import uk_date
from utils.firestore_client import cancel_booking, list_user_bookings
from utils.styles import apply_lato_font

# ---------------------------------------------------
# PAGE SETUP
# ---------------------------------------------------
apply_lato_font()
st.title("My Bookings")
ensure_db()

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
# FETCH BOOKINGS
# ---------------------------------------------------
bookings = list_user_bookings(user_id, include_cancelled=True)
upcoming = sorted(
    [
        booking
        for booking in bookings
        if booking.booking_date >= today_str and booking.status == "active"
    ],
    key=lambda booking: (booking.booking_date, booking.start_time),
)
past = sorted(
    [
        booking
        for booking in bookings
        if booking.booking_date < today_str or booking.status != "active"
    ],
    key=lambda booking: (booking.booking_date, booking.start_time),
    reverse=True,
)

# ---------------------------------------------------
# SHOW UPCOMING BOOKINGS
# ---------------------------------------------------
st.subheader("Upcoming Bookings")

if not upcoming:
    st.info("You have no upcoming bookings.")
else:
    for booking in upcoming:
        with st.container():
            st.markdown(
                f"""
                **Desk {booking.desk_id}**  
                • Date: **{uk_date(booking.booking_date)}**  
                • Time: **{booking.start_time}–{booking.end_time}**  
                • Status: **{booking.status}**  
                • Checked in: **{'Yes' if booking.checked_in else 'No'}**
                """
            )

            if st.button("Cancel Booking", key=f"cancel_{booking.booking_id}"):
                cancel_booking(
                    booking.booking_id,
                    cancelled_by=st.session_state.user_email,
                )

                log_action(
                    "BOOKING_CANCELLED",
                    f"booking_id={booking.booking_id}, desk_id={booking.desk_id}",
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
    for booking in past:
        st.markdown(
            f"""
            **Desk {booking.desk_id}**  
            • Date: **{uk_date(booking.booking_date)}**  
            • Time: **{booking.start_time}–{booking.end_time}**  
            • Status: **{booking.status}**  
            • Checked in: **{'Yes' if booking.checked_in else 'No'}**
            """
        )
        st.divider()
