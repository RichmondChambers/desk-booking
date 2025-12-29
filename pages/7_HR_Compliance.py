import streamlit as st
import pandas as pd
from utils.auth import require_admin
from utils.db import ensure_db
from utils.firestore_client import list_all_bookings
from utils.firestore_users import list_users
from utils.styles import apply_lato_font

apply_lato_font()
st.title("HR Compliance Reporting")
ensure_db()
require_admin()

# No-show report
st.subheader("No-show Records")
no_shows = list_all_bookings({"status": "no_show"})
if no_shows:
    df_nos = pd.DataFrame(
        [
            {
                "Booking ID": booking.booking_id,
                "User": booking.user_name,
                "Email": booking.user_email,
                "Date": booking.booking_date,
                "Start": booking.start_time,
                "End": booking.end_time,
            }
            for booking in no_shows
        ]
    )
    st.dataframe(df_nos)
else:
    st.info("No no-show records found.")

# Attendance summary
st.subheader("Attendance Summary")
users = list_users()

bookings = list_all_bookings()
attendance_map = {
    user.user_id: {
        "name": user.name,
        "email": user.email,
        "attended": 0,
        "no_shows": 0,
    }
    for user in users
}
for booking in bookings:
    record = attendance_map.get(booking.user_id)
    if not record:
        continue
    if booking.checked_in:
        record["attended"] += 1
    if booking.status == "no_show":
        record["no_shows"] += 1

df_att = pd.DataFrame(
    [
        {
            "User": record["name"],
            "Email": record["email"],
            "Attended": record["attended"],
            "No Shows": record["no_shows"],
        }
        for record in attendance_map.values()
    ]
)
st.dataframe(df_att)
