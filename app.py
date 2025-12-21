import streamlit as st
from datetime import datetime, date
from authlib.integrations.requests_client import OAuth2Session

from utils.db import init_db, get_conn
from utils.rules import enforce_no_shows
from utils.audit import audit_log

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------
st.set_page_config(page_title="Desk Booking", layout="wide")

OAUTH = st.secrets["oauth"]
CLIENT_ID = OAUTH["client_id"]
CLIENT_SECRET = OAUTH["client_secret"]
REDIRECT_URI = OAUTH["redirect_uri"]  # MUST BE EXACT MATCH TO GOOGLE CONSOLE
ALLOWED_DOMAIN = OAUTH["allowed_domain"]
APP_URL = OAUTH["app_url"]

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# ---------------------------------------------------
# LOGIN SCREEN
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
        prompt="consent"
    )

    st.title("Richmond Chambers – Internal Tool")
    st.write("Please sign in with your Richmond Chambers Google Workspace account.")
    st.markdown(f"[Sign in with Google]({auth_url})", unsafe_allow_html=True)
    st.stop()

# ---------------------------------------------------
# OAUTH CALLBACK HANDLING
# ---------------------------------------------------
params = st.query_params

if "token" not in st.session_state:

    if "code" in params:   # Google sent us an authorization code
        code = params["code"]

        oauth = OAuth2Session(
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT_URI,
        )

        token = oauth.fetch_token(
            TOKEN_URL,
            code=code,
            client_secret=CLIENT_SECRET
        )

        st.session_state["token"] = token

        # CLEAN URL
        st.query_params.clear()

        # REFRESH CLEAN PAGE
        st.markdown(f'<meta http-equiv="refresh" content="0;url={APP_URL}" />', unsafe_allow_html=True)
        st.stop()

    # No token → show login button
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

if not email.endswith("@" + ALLOWED_DOMAIN):
    st.error(f"Access denied — please use a @{ALLOWED_DOMAIN} account.")
    st.stop()

name = userinfo.get("name") or email.split("@")[0]

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
    c.execute("INSERT INTO users (name, email, role, can_book) VALUES (?, ?, 'user', 1)",
              (name, email))
    conn.commit()
    row = c.execute(
        "SELECT id, name, role, can_book FROM users WHERE email=?",
        (email,)
    ).fetchone()

conn.close()

# ---------------------------------------------------
# STORE SESSION
# ---------------------------------------------------
st.session_state.user_id = row[0]
st.session_state.user_name = row[1]
st.session_state.role = row[2]
st.session_state.can_book = row[3]
st.session_state.user_email = email

# ---------------------------------------------------
# SIDEBAR
# ---------------------------------------------------
st.sidebar.write(f"**User:** {name}")
st.sidebar.write(f"**Role:** {row[2]}")

# ---------------------------------------------------
# MAIN PAGE
# ---------------------------------------------------
st.title("Desk Booking System")
st.write("Use the sidebar to navigate options.")
