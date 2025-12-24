import streamlit as st
import requests
from google_auth_oauthlib.flow import Flow

from utils.auth import require_login
from utils.db import init_db, seed_desks, get_conn

# ---------------------------------------------------
# STREAMLIT CONFIG
# ---------------------------------------------------
st.set_page_config(page_title="Desk Booking", layout="wide")

# ---------------------------------------------------
# BOOTSTRAP ADMINS (CANNOT BE LOST)
# ---------------------------------------------------
BOOTSTRAP_ADMINS = {
    "paul.richmond@richmondchambers.com",
}

# ---------------------------------------------------
# INITIALISE DATABASE + SEED DATA
# ---------------------------------------------------
init_db()
seed_desks()

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

    conn = get_conn()
    c = conn.cursor()

    row = c.execute(
        """
        SELECT id, name, role, can_book, is_active
        FROM users
        WHERE email = ?
        """,
        (email,),
    ).fetchone()

    # FIRST LOGIN → CREATE USER
    if not row:
        initial_role = "admin" if email in BOOTSTRAP_ADMINS else "user"

        c.execute(
            """
            INSERT INTO users (name, email, role, can_book, is_active)
            VALUES (?, ?, ?, 1, 1)
            """,
            (name, email, initial_role),
        )
        conn.commit()

        row = c.execute(
            """
            SELECT id, name, role, can_book, is_active
            FROM users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()

    # BLOCK DEACTIVATED USERS
    if row[4] == 0:
        conn.close()
        st.error(
            "Your account has been deactivated. "
            "Please contact an administrator."
        )
        st.stop()

    db_role = row[2]

    # 🔒 BOOTSTRAP OVERRIDE ALWAYS WINS
    if email in BOOTSTRAP_ADMINS:
        final_role = "admin"

        # Optional: keep DB in sync
        if db_role != "admin":
            c.execute(
                "UPDATE users SET role='admin' WHERE email=?",
                (email,),
            )
            conn.commit()
    else:
        final_role = db_role

    conn.close()

    st.session_state.user_id = row[0]
    st.session_state.user_name = row[1]
    st.session_state.user_email = email
    st.session_state.role = final_role
    st.session_state.can_book = row[3]

# ---------------------------------------------------
# SIDEBAR
# ---------------------------------------------------
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Email:** {st.session_state.user_email}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")

st.sidebar.divider()

if st.sidebar.button("Log out"):
    logout()

# ---------------------------------------------------
# MAIN APP
# ---------------------------------------------------
st.title("Desk Booking System")
st.write("Use the sidebar to navigate between booking functions.")
