import streamlit as st
import requests
from google_auth_oauthlib.flow import Flow

from utils.auth import require_login
from utils.db import init_db, get_conn

st.set_page_config(page_title="Desk Booking", layout="wide")

# ---------------------------------------------------
# HANDLE OAUTH CALLBACK
# ---------------------------------------------------
query_params = st.query_params

if "code" in query_params and "oauth_email" not in st.session_state:

    if "oauth_state" not in st.session_state:
        st.error("OAuth state missing. Please click 'Sign in with Google' again.")
        st.stop()

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": st.secrets["oauth"]["client_id"],
                "client_secret": st.secrets["oauth"]["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [st.secrets["oauth"]["redirect_uri"]],
            }
        },
        scopes=["openid", "email", "profile"],
        state=st.session_state["oauth_state"],
        redirect_uri=st.secrets["oauth"]["redirect_uri"],
    )

    flow.fetch_token(code=query_params["code"])
    credentials = flow.credentials

    userinfo = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {credentials.token}"},
        timeout=10,
    ).json()

    email = (userinfo.get("email") or "").lower()
    name = userinfo.get("name") or email.split("@")[0]

    if not email.endswith("@richmondchambers.com"):
        st.error("Access restricted to Richmond Chambers staff.")
        st.stop()

    st.session_state["oauth_email"] = email
    st.session_state["oauth_name"] = name

    # cleanup
    st.session_state.pop("oauth_state", None)
    st.query_params.clear()

# ---------------------------------------------------
# REQUIRE LOGIN (shows sign-in link and stops if not logged in)
# ---------------------------------------------------
require_login()

# ---------------------------------------------------
# INITIALISE DATABASE
# ---------------------------------------------------
init_db()


# ---------------------------------------------------
# INITIALISE SESSION DEFAULTS
# ---------------------------------------------------
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", None)
st.session_state.setdefault("user_name", None)
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)

# ---------------------------------------------------
# AUTHENTICATION (STRICT)
# ---------------------------------------------------
if st.session_state.user_id is None:

    user = st.experimental_user  # provided only when Cloud auth is enabled

    # ---- HARD FAIL IF AUTHENTICATION NOT ENABLED ----
    if user is None:
        st.title("Desk Booking System")
        st.error(
            "Authentication failed: Streamlit did not provide a user identity.\n\n"
            "Please ensure **User Authentication is enabled** in Streamlit Cloud."
        )
        st.stop()

    # Extract authenticated email
    email = getattr(user, "email", None)
    name = getattr(user, "name", None)

    if email is None:
        st.title("Desk Booking System")
        st.error(
            "Authentication error: No email address was provided by Streamlit.\n\n"
            "Only authenticated @richmondchambers.com users may access this system."
        )
        st.stop()

    email = email.lower()
    name = name or email.split("@")[0]

    # ---- STRICT DOMAIN ENFORCEMENT ----
    if not email.endswith("@richmondchambers.com"):
        st.title("Desk Booking System")
        st.error("Access denied — only @richmondchambers.com accounts can use this system.")
        st.stop()

    # ---------------------------------------------------
    # LOOK UP OR CREATE USER IN DATABASE
    # ---------------------------------------------------
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

    # Save into session state
    st.session_state.user_id = row[0]
    st.session_state.user_name = row[1]
    st.session_state.role = row[2]
    st.session_state.can_book = row[3]
    st.session_state.user_email = email

# ---------------------------------------------------
# SIDEBAR
# ---------------------------------------------------
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Email:** {st.session_state.user_email}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")

st.title("Desk Booking System")
st.write("Use the sidebar to navigate between booking functions.")
