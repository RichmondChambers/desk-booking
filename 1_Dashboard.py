import streamlit as st
import pandas as pd
from datetime import date
from utils.db import get_conn
from utils.rules import enforce_no_shows

st.title("Desk Availability")

# Enforce no-shows on page load
enforce_no_shows()

selected_date = st.date_input("Select date", date.today())

conn = get_conn()

desks = pd.read_sql(
    "SELECT id, name, desk_type FROM desks WHERE active=1 ORDER BY id",
    conn
)

bookings = pd.read_sql(
    """
    SELECT b.desk_id, u.name AS user_name, b.start_time, b.end_time, b.checked_in
    FROM bookings b
    JOIN users u ON u.id=b.user_id
    WHERE b.date=? AND b.status='booked'
    ORDER BY b.start_time
    """,
    conn,
    params=(str(selected_date),),
)

conn.close()

for _, desk in desks.iterrows():
    st.subheader(f"{desk['name']} ({desk['desk_type']})")
    desk_bookings = bookings[bookings["desk_id"] == desk["id"]]

    if desk_bookings.empty:
        st.success("Available (no bookings)")
    else:
        for _, row in desk_bookings.iterrows():
            status = "✅" if int(row["checked_in"]) == 1 else "⏳"
            st.write(
                f"{row['start_time']}–{row['end_time']} · "
                f"{row['user_name']} · {status}"
            )

    st.divider()
