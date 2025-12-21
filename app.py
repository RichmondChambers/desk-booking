import streamlit as st
from datetime import datetime, date
from authlib.integrations.requests_client import OAuth2Session

from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log


# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------
st.set_page_config(page_title="Desk Booking", layout="wide")


# ---------------------------------------------------
# LOAD OAUTH SETTINGS
# ---------------------------------------------------
OAUTH = st.secrets["oauth"]

CLIENT_ID = OAUTH["client_id"]
CLIENT_SECRET = OAUTH["client_secret"]
REDIRECT_URI = OAUTH["redirect_uri"]     # MUST use query param callback
ALLOWED_DOMAIN = OAUTH["allowed_domain"].lower()
APP_URL = OAUTH["app_url"]

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


# ---------------------------------------------------
# LOGIN SCREEN
# ---------------------------------------------------
def show_login_screen():
    oauth = OAuth2Session(
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        scope="openid email profile"
    )

    auth_url, _ = oauth.create_authorization_url(
        AUTH_URL,
        access_type="offline",
        prompt="consent"
    )

    st.title("Richmond Chambers – Internal Tool")
    st.write("Please sign in with your Richmond Chambers Google Workspace account.")
    st.markdown(f"[**Sign in with Google**]({auth_url})", unsafe_allow_html=True)
    st.stop()


# ---------------------------------------------------
# HANDLE GOOGLE OAUTH CALLBACK (?oauth2callback=true&code=XYZ)
# ---------------------------------------------------
params = st.query_params

if "token" not in st.session_state:

    # Google redirected back with auth code
    if "oauth2callback" in params and "code" in params:

        code = params["code"]

        oauth = OAuth2Session(
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT_URI,
        )

        # Exchange code for token
        token = oauth.fetch_token(
            TOKEN_URL,
            code=code,
            client_secret=CLIENT_SECRET
        )

        st.session_state["token"] = token

        # Remove query parameters entirely
        st.query_params.clear()

        # Force clean reload to root without params
        st.markdown(
            f'<meta http-equiv="refresh" content="0;url={APP_URL}" />',
            unsafe_allow_html=True
        )
        st.stop()

    # No token & no callback → show login
    show_login_screen()



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
    st.error(f"Access denied. Please sign in using a @{ALLOWED_DOMAIN} Google account.")
    st.stop()


# ---------------------------------------------------
# DATABASE USER HANDLING
# ---------------------------------------------------
init_db()
conn = get_conn()
c = conn.cursor()

row = c.execute(
    "SELECT id, name, role, can_book FROM users WHERE email=?",
    (email,)
).fetchone()

if not row:
    c.execute("""
        INSERT INTO users (name, email, role, can_book)
        VALUES (?, ?, 'user', 1)
    """, (name, email))
    conn.commit()

    row = c.execute(
        "SELECT id, name, role, can_book FROM users WHERE email=?",
        (email,)
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
# SIDEBAR INFO
# ---------------------------------------------------
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")


# ---------------------------------------------------
# AUTOMATIC NO-SHOW ENFORCEMENT
# ---------------------------------------------------
enforce_no_shows(datetime.now())


# ---------------------------------------------------
# QR CHECK-IN HANDLER
# ---------------------------------------------------
params = st.query_params

if "checkin" in params:
    try:
        desk_id = int(params["checkin"])
        today = date.today().strftime("%Y-%m-%d")
        now_time = datetime.now().strftime("%H:%M")

        conn = get_conn()
        c = conn.cursor()

        booking = c.execute("""
            SELECT id, start_time, end_time, checked_in
            FROM bookings
            WHERE user_id=? AND desk_id=? AND date=? AND status='booked'
        """, (st.session_state.user_id, desk_id, today)).fetchone()

        if not booking:
            st.warning("No active booking found for this desk today.")
        else:
            booking_id, start_t, end_t, checked_in = booking

            if checked_in:
                st.info("Already checked in.")
            elif start_t <= now_time <= end_t:
                c.execute("UPDATE bookings SET checked_in=1 WHERE id=?", (booking_id,))
                conn.commit()
                audit_log(email, "QR_CHECK_IN", f"booking={booking_id}, desk={desk_id}")
                st.success("Checked in successfully.")
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
