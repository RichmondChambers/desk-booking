import streamlit as st
import pandas as pd
from utils.db import get_conn

if st.session_state.role != "admin":
    st.error("Admin access only.")
    st.stop()

st.title("Admin Panel")

conn = get_conn()
c = conn.cursor()

# View all users
st.subheader("Users")
users = c.execute("SELECT id, name, email, role, can_book FROM users").fetchall()
df_users = pd.DataFrame(users, columns=["ID", "Name", "Email", "Role", "Can Book"])
st.dataframe(df_users)

# Modify user
st.subheader("Modify User Permissions")

target_email = st.text_input("User email to modify")
new_role = st.selectbox("New role", ["user", "admin"])
new_can_book = st.selectbox("Booking Permission", [0, 1])

if st.button("Update User"):
    c.execute(
        "UPDATE users SET role=?, can_book=? WHERE email=?",
        (new_role, new_can_book, target_email),
    )
    conn.commit()
    st.success("User updated.")

# View all bookings
st.subheader("All Bookings")
bookings = c.execute("""
    SELECT id, user_id, desk_id, date, start_time, end_time, status, checked_in
    FROM bookings
    ORDER BY date DESC
""").fetchall()
df_bookings = pd.DataFrame(
    bookings,
    columns=["ID", "User ID", "Desk", "Date", "Start", "End", "Status", "Checked In"],
)
st.dataframe(df_bookings)

conn.close()
