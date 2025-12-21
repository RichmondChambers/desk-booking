import streamlit as st
from datetime import datetime, date
from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log

st.set_page_config(page_title="Desk Booking", layout="wide")

# -----------------------------
# GOOGLE LOGIN (Streamlit Auth)
# -----------------------------
from streamlit_auth import GoogleAuth

auth = GoogleAuth(
    client_id=st.secrets["GOOGLE_CLIENT_ID"],
    client_secret=st.secrets["GOOGLE_CLIENT_SECRET"],
    redirect_uri="https://richmond-chambers-desk-booking.streamlit.app/oauth2callback",
    scope=["openid", "email", "profile"],
)

user_info = auth.login()

# Show login screen if not authenticated
if not user_info:
    st.title("Richmond Chambers – Internal Tool")
    st.write("Please sign in with a Richmond Chambers Google Workspace account to access this app.")
    auth.render_login_button()
    st.stop()

# Restrict domain
email = user_info["email"]
if not email.endswith(st.secrets["ALLOWED_DOMAIN"]):
    st.error("Access denied. You must use a @richmondchambers.com account.")
    st.stop()

name = user_info.get("name", email.split("@")[0])

# -----------------------------
# DATABASE USER HANDLING
# -----------------------------
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

st.session_state.user_id = row[0]
st.session_state.user_name = row[1]
st.session_state.role = row[2]
st.session_state.can_book = row[3]
st.session_state.user_email = email

# Sidebar info
st.sidebar.markdown(f"**User:** {name}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")

# Enforce no-shows
enforce_no_shows(datetime.now())

st.title("Desk Booking System")
st.write("Use the sidebar to navigate between functions.")
