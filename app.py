import requests
import streamlit as st
from google_auth_oauthlib.flow import Flow

from utils.auth import require_login
from utils.db import ensure_db
from utils.firestore_users import create_user, get_user_by_email, update_user
from utils.styles import apply_lato_font

# ---------------------------------------------------
# STREAMLIT CONFIG
# ---------------------------------------------------
st.set_page_config(page_title="Desk Booking", layout="wide")
apply_lato_font()

# ---------------------------------------------------
# BOOTSTRAP ADMINS (CANNOT BE LOST)
# ---------------------------------------------------
BOOTSTRAP_ADMINS = {
    "paul.richmond@richmondchambers.com",
}

# ---------------------------------------------------
# INITIALISE DATABASE
# ---------------------------------------------------
ensure_db()

# ---------------------------------------------------
# LOGOUT FUNCTION
# ---------------------------------------------------
def logout():
    for key in [
        "oauth_email",
        "oauth_name",
        "user_id",
        "user_email",
        "user_name",
        "role",
        "can_book",
    ]:
        st.session_state.pop(key, None)

    st.query_params.clear()
    st.rerun()

# ---------------------------------------------------
# HANDLE OAUTH CALLBACK
# ---------------------------------------------------
query_params = st.query_params

if "code" in query_params and "oauth_email" not in st.session_state:

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": st.secrets["oauth"]["client_id"],
                "client_secret": st.secrets["oauth"]["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [st.secrets["oauth"]["redirect_uri"]],
            }
        },
        scopes=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ],
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

    # Restrict domain AFTER login
    if not email.endswith("@richmondchambers.com"):
        st.error("Access restricted to Richmond Chambers staff.")
        st.stop()

    st.session_state["oauth_email"] = email
    st.session_state["oauth_name"] = name
    st.query_params.clear()

# ---------------------------------------------------
# REQUIRE LOGIN
# ---------------------------------------------------
if "code" not in st.query_params:
    require_login()

# ---------------------------------------------------
# INITIALISE SESSION DEFAULTS
# ---------------------------------------------------
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", None)
st.session_state.setdefault("user_name", None)
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)

# ---------------------------------------------------
# MAP OAUTH USER → LOCAL USER RECORD
# ---------------------------------------------------
if st.session_state.user_id is None:

    email = st.session_state["oauth_email"]
    name = st.session_state["oauth_name"]

    user = get_user_by_email(email)

    # FIRST LOGIN → CREATE USER
    if not user:
        initial_role = "admin" if email in BOOTSTRAP_ADMINS else "user"
        user = create_user(name=name, email=email, role=initial_role)

    # BLOCK DEACTIVATED USERS
    if not user.is_active:
        st.error(
            "Your account has been deactivated. "
            "Please contact an administrator."
        )
        st.stop()

    db_role = user.role

    # 🔒 BOOTSTRAP OVERRIDE ALWAYS WINS
    if email in BOOTSTRAP_ADMINS:
        final_role = "admin"

        if db_role != "admin":
            update_user(email, {"role": "admin"})
    else:
        final_role = db_role

    st.session_state.user_id = user.user_id
    st.session_state.user_name = user.name
    st.session_state.user_email = email
    st.session_state.role = final_role
    st.session_state.can_book = user.can_book

with st.sidebar:
    # ---------------------------------------------------
    # SIDEBAR
    # ---------------------------------------------------
    st.image("assets/logo.svg", use_container_width=True)

    st.divider()

    st.markdown(f"**User:** {st.session_state.user_name}")
    st.markdown(f"**Email:** {st.session_state.user_email}")
    st.markdown(f"**Role:** {st.session_state.role}")

    st.divider()

    if st.button("Log out"):
        logout()

# ---------------------------------------------------
# MAIN APP
# ---------------------------------------------------
st.title("Desk Booking System")
st.write("Use the sidebar to navigate between booking functions.")
