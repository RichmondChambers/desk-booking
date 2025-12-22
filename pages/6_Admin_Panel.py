import streamlit as st
import pandas as pd
from utils.db import get_conn
from utils.permissions import require_admin

st.set_page_config(page_title="Admin Panel", layout="wide")

# ---------------------------------------------------
# PERMISSION CHECK
# ---------------------------------------------------
require_admin()

st.title("Admin Panel")

# ---------------------------------------------------
# LOAD USERS
# ---------------------------------------------------
conn = get_conn()
c = conn.cursor()

users = c.execute(
    """
    SELECT id, name, email, role, can_book
    FROM users
    ORDER BY email
    """
).fetchall()

# ---------------------------------------------------
# USER MANAGEMENT
# ---------------------------------------------------
st.subheader("User Management")

for user_id, name, email, role, can_book in users:

    is_self = email == st.session_state.user_email

    with st.container(border=True):
        col1, col2, col3, col4, col5 = st.columns([3, 4, 2, 2, 3])

        col1.markdown(f"**{name}**")
        col2.markdown(email)
        col3.markdown(f"Role: **{role}**")
        col4.markdown(f"Can book: **{'Yes' if can_book else 'No'}**")

        with col5:
            # ---- ROLE TOGGLE ----
            if role == "admin":
                if st.button(
                    "Remove admin",
                    key=f"remove_admin_{user_id}",
                    disabled=is_self,
                ):
                    conn = get_conn()
                    conn.execute(
                        "UPDATE users SET role='user' WHERE id=?",
                        (user_id,),
                    )
                    conn.commit()
                    conn.close()
                    st.experimental_rerun()
            else:
                if st.button(
                    "Make admin",
                    key=f"make_admin_{user_id}",
                    disabled=is_self,
                ):
                    conn = get_conn()
                    conn.execute(
                        "UPDATE users SET role='admin' WHERE id=?",
                        (user_id,),
                    )
                    conn.commit()
                    conn.close()
                    st.experimental_rerun()

            # ---- BOOKING PERMISSION TOGGLE ----
            toggle_label = "Disable booking" if can_book else "Enable booking"

            if st.button(
                toggle_label,
                key=f"toggle_booking_{user_id}",
                disabled=is_self,
            ):
                conn = get_conn()
                conn.execute(
                    "UPDATE users SET can_book=? WHERE id=?",
                    (0 if can_book else 1, user_id),
                )
                conn.commit()
                conn.close()
                st.experimental_rerun()

st.divider()

# ---------------------------------------------------
# BOOKINGS OVERVIEW (READ-ONLY)
# ---------------------------------------------------
st.subheader("All Bookings")

bookings = c.execute(
    """
    SELECT id, user_id, desk_id, date, start_time, end_time, status, checked_in
    FROM bookings
    ORDER BY date DESC
    """
).fetchall()

df_bookings = pd.DataFrame(
    bookings,
    columns=[
        "ID",
        "User ID",
        "Desk",
        "Date",
        "Start",
        "End",
        "Status",
        "Checked In",
    ],
)

st.dataframe(df_bookings, use_container_width=True)

conn.close()
