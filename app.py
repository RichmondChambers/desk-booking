import streamlit as st
from datetime import datetime, date

from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log

from authlib.integrations.requests_client import OAuth2Session


# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------
st.set_page_config(
    page_title="Desk Booking",
    layout="wide",
)


# ---------------------------------------------------
# LOAD OAUTH SETTINGS
# ---------------------------------------------------
CLIENT_ID = st.secrets["oauth"]["client_id"]
CLIENT_SECRET = st.secrets["oauth"]["client_secret"]
REDIRECT_URI = st.secrets["oauth"]["redirect_uri"]
ALLOWED_DOMAIN = st.secrets["oauth"]["allowed_domain"].lower()
APP_URL = st.secrets["oauth"]["app_url"]

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


# ---------------------------------------------------
# LOGIN SCREEN
# ---------------------------------------------------
def show_login_screen():
    oauth = OAuth2Session(
        CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        scope="openid email profile",
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

    # Callback stage — user returned from Google with ?code=
    if "code" in qp:
        code = qp["code"]

        oauth = OAuth2Session(
            CLIENT_ID,
            CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
        )

        token = oauth.fetch_token(
            TOKEN_URL,
            code=code,
            grant_type="authorization_code",
        )

        # Save session token
        st.session_state["token"] = token

        # Clear the URL query params
        st.query_params.clear()

        # Force redirect to home WITHOUT params
        st.markdown(
            f'<meta http-equiv="refresh" content="0;url={APP_URL}" />',
            unsafe_allow_html=True
        )
        st.stop()

    # Not logged in → show login button
    show_login_screen()


# ---------------------------------------------------
# FETCH USER INFO (NOW AUTHENTICATED)
# ---------------------------------------------------
oauth = OAuth2Session(
    CLIENT_ID,
    CLIENT_SECRET,
    token=st.session_state["token"]
)

userinfo = oauth.get(USERINFO_URL).json()

email = (userinfo.get("email") or "").lower()
name = userinfo.get("name") or email.split("@")[0]


# ---------------------------------------------------
# RESTRICT LOGIN TO CORPORATE DOMAIN
# ---------------------------------------------------
if not email.endswith("@" + ALLOWED_DOMAIN):
    st.error(f"Access denied. Please use a @{ALLOWED_DOMAIN} Google Workspace account.")
    st.stop()


# ---------------------------------------------------
# DATABASE USER CREATION / LOADING
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
# SIDEBAR INFO
# ---------------------------------------------------
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")


# ---------------------------------------------------
# NO-SHOW ENFORCEMENT
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
            st.warning("No active booking found for this desk today.")

        else:
            booking_id, start_time, end_time, checked_in = booking

            if checked_in:
                st.info("Already checked in.")

            elif start_time <= now_hhmm <= end_time:
                c.execute("UPDATE bookings SET checked_in=1 WHERE id=?", (booking_id,))
                conn.commit()

                audit_log(
                    st.session_state.user_email,
                    "QR_CHECK_IN",
                    f"booking={booking_id}, desk={desk_id}"
                )

                st.success("Checked in successfully!")

            else:
                st.warning(f"Booking not active. Valid window: {start_id}-{end_time}")

        conn.close()

    finally:
        st.query_params.clear()
        st.rerun()


# ---------------------------------------------------
# MAIN PAGE
# ---------------------------------------------------
st.title("Desk Booking System")
st.write("Use the sidebar to navigate between system functions.")
