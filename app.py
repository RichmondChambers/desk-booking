import streamlit as st
from datetime import datetime, date

from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log

# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------
st.set_page_config(page_title="Desk Booking", layout="wide")

# ---------------------------------------------------
# STREAMLIT CLOUD AUTHENTICATION
# ---------------------------------------------------
user = st.experimental_user

if not user or not user.is_authenticated:
    st.title("Desk Booking")
    st.write("Please sign in using your Richmond Chambers Google account.")
    st.stop()

email = user.email.lower()
name = user.name or email.split("@")[0]

# Domain restriction (failsafe)
if not email.endswith("@richmondchambers.com"):
    st.error("Access denied — please use your @richmondchambers.com Google account.")
    st.stop()

# ---------------------------------------------------
# DATABASE USER HANDLING
# ---------------------------------------------------
init_db()
conn = get_conn()
c = conn.cursor()

row = c.execute(
    "SELECT id, name, role, can_book FROM users WHERE email=?",
    (email,),
).fetchone()

if not row:
    c.execute(
        "INSERT INTO users (name, email, role, can_book) VALUES (?, ?, 'user', 1)",
        (name, email),
    )
    conn.commit()
    row = c.execute(
        "SELECT id, name, role, can_book FROM users WHERE email=?",
        (email,),
    ).fetchone()

conn.close()

# ---------------------------------------------------
# SAVE USER IN SESSION
# ---------------------------------------------------
st.session_state.user_id = row[0]
st.session_state.user_name = row[1]
st.session_state.role = row[2]
st.session_state.can_book = row[3]
st.session_state.user_email = email

# ---------------------------------------------------
# SIDEBAR USER INFO
# ---------------------------------------------------
st.sidebar.markdown(f"**User:** {name}")
st.sidebar.markdown(f"**Email:** {email}")
st.sidebar.markdown(f"**Role:** {row[2]}")

# ---------------------------------------------------
# ENFORCE NO-SHOWS
# ---------------------------------------------------
enforce_no_shows(datetime.now())

# ---------------------------------------------------
# MAIN PAGE
# ---------------------------------------------------
st.title("Desk Booking System")
st.write("Use the sidebar to navigate between system functions.")
