import streamlit as st
st.write("DEBUG — QUERY PARAMS:", st.query_params)

import streamlit as st
from datetime import datetime, date

from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log

# CORRECT AUTHLIB IMPORT
from authlib.integrations.requests_client import OAuth2Session


# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------
st.set_page_config(page_title="Desk Booking", layout="wide")


# ---------------------------------------------------
# LOAD OAUTH SECRETS
# ---------------------------------------------------
OAUTH = st.secrets["oauth"]

CLIENT_ID = OAUTH["client_id"]
CLIENT_SECRET = OAUTH["client_secret"]
REDIRECT_URI = OAUTH["redirect_uri"]
ALLOWED_DOMAIN = OAUTH["allowed_domain"].lower()
APP_URL = OAUTH["app_url"]

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


# ---------------------------------------------------
# LOGIN PAGE
# ---------------------------------------------------
def show_login():
    oauth = OAuth2Session(
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        scope="openid email profile"
    )

    auth_url, _ = oauth.create_authorization_url(
        AUTH_URL,
        access_type="offline",
        prompt="consent",
    )

    st.title("Richmond Chambers – Internal Tool")
    st.write("Please sign in with your Richmond Chambers Google Workspace account.")
    st.markdown(f"[**Sign in with Google**]({auth_url})", unsafe_allow_html=True)
    st.stop()


# ---------------------------------------------------
# HANDLE GOOGLE CALLBACK (?code=…)
# ---------------------------------------------------
if "token" not in st.session_state:

    qp = st.query_params

    if "code" in qp:
        code = qp["code"]

        oauth = OAuth2Session(
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT_URI
        )

        token = oauth.fetch_token(
            TOKEN_URL,
            code=code,
            client_secret=CLIENT_SECRET
        )

        st.session_state["token"] = token

        # Clear query parameters from URL
        st.query_params.clear()

        # Redirect cleanly to root
        st.markdown(
            f'<meta http-equiv="refresh" content="0;url={APP_URL}" />',
            unsafe_allow_html=True
        )
        st.stop()

    # Otherwise show login
    show_login()


# ---------------------------------------------------
# FETCH USER INFO
# ---------------------------------------------------
oauth = OAuth2Session(
    client_id=CLIENT_ID,
    token=st.session_state["token"]
)

userinfo = oauth.get(USERINFO_URL).json()

email = userinfo.get("email", "").lower()
name = userinfo.get("name") or email.split("@")[0]


# ---------------------------------------------------
# DOMAIN RESTRICTION
# ---------------------------------------------------
if not email.endswith("@" + ALLOWED_DOMAIN):
    st.error(f"Access denied. Please use a @{ALLOWED_DOMAIN} account.")
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
    c.execute("""
        INSERT INTO users (name, email, role, can_book)
        VALUES (?, ?, 'user', 1)
    """, (name, email))
    conn.commit()

    row = c.execute("""
        SELECT id, name, role, can_book
        FROM users WHERE email=?
    """, (email,)).fetchone()

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
# SIDEBAR
# ---------------------------------------------------
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")


# ---------------------------------------------------
# ENFORCE NO-SHOWS
# ---------------------------------------------------
enforce_no_shows(datetime.now())


# ---------------------------------------------------
# QR CHECK-IN HANDLER
# ---------------------------------------------------
qp = st.query_params

if "checkin" in qp:
    try:
        desk_id = int(qp["checkin"])
        today = date.today().strftime("%Y-%m-%d")
        now_hhmm = datetime.now().strftime("%H:%M")

        conn = get_conn()
        c = conn.cursor()

        booking = c.execute("""
            SELECT id, start_time, end_time, checked_in
            FROM bookings
            WHERE user_id=? AND desk_id=? AND date=? AND status='booked'
        """, (st.session_state.user_id, desk_id, today)).fetchone()

        if not booking:
            st.warning("No active booking found.")
        else:
            booking_id, start_t, end_t, checked_in = booking

            if checked_in:
                st.info("Already checked in.")
            elif start_t <= now_hhmm <= end_t:
                c.execute("UPDATE bookings SET checked_in=1 WHERE id=?", (booking_id,))
                conn.commit()
                audit_log(email, "QR_CHECK_IN", f"booking={booking_id}, desk={desk_id}")
                st.success("Checked in successfully!")
            else:
                st.warning(f"Booking active only between {start_t}–{end_t}")

        conn.close()

    finally:
        st.query_params.clear()
        st.rerun()


# ---------------------------------------------------
# MAIN PAGE
# ---------------------------------------------------
st.title("Desk Booking System")
st.write("Use the sidebar to navigate between system functions.")
