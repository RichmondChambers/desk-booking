import json
import streamlit as st
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests
from utils.db import get_conn

SCOPES = ["openid", "email", "profile"]

def _oauth_config() -> dict:
    # Prefer Streamlit Cloud secrets, fall back to local file
    if "google_oauth" in st.secrets:
        return {
            "web": {
                "client_id": st.secrets["google_oauth"]["client_id"],
                "client_secret": st.secrets["google_oauth"]["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [st.secrets["google_oauth"]["redirect_uri"]],
            }
        }
    with open("client_secret.json", "r", encoding="utf-8") as f:
        return json.load(f)

def _settings():
    allowed_domain = st.secrets.get("app", {}).get("allowed_domain", "yourdomain.com")
    redirect_uri = st.secrets.get("google_oauth", {}).get("redirect_uri", "http://localhost:8501")
    return allowed_domain, redirect_uri

def google_login_link():
    allowed_domain, redirect_uri = _settings()
    client_config = _oauth_config()

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )

    auth_url, state = flow.authorization_url(
        access_type="online",
        include_granted_scopes="true",
        prompt="select_account"
    )

    # Persist state BEFORE redirect
    st.session_state["oauth_state"] = state
    st.session_state["oauth_started"] = True

    st.markdown(f"[Sign in with Google]({auth_url})")

def handle_oauth_response() -> None:
    qp = st.query_params.to_dict()

    if "code" not in qp:
        return

    if "oauth_state" not in st.session_state:
        return

    allowed_domain, redirect_uri = _settings()
    client_config = _oauth_config()

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=st.session_state["oauth_state"],
        redirect_uri=redirect_uri
    )

    flow.fetch_token(code=qp["code"])
    creds = flow.credentials

    info = id_token.verify_oauth2_token(
        creds.id_token,
        requests.Request(),
        client_config["web"]["client_id"]
    )

    email = info["email"]
    domain = email.split("@", 1)[1]
    if domain.lower() != allowed_domain.lower():
        st.error("Unauthorised Google Workspace domain.")
        return

    conn = get_conn()
    c = conn.cursor()

    user = c.execute(
        "SELECT id, name, role, can_book FROM users WHERE email=?",
        (email,)
    ).fetchone()

    if not user:
        c.execute(
            "INSERT INTO users (name, email, role, can_book) VALUES (?, ?, 'user', 1)",
            (info.get("name") or email.split("@")[0], email)
        )
        conn.commit()
        user = c.execute(
            "SELECT id, name, role, can_book FROM users WHERE email=?",
            (email,)
        ).fetchone()

    conn.close()

    st.session_state.update({
        "user_id": user[0],
        "user_name": user[1],
        "role": user[2],
        "can_book": user[3],
        "user_email": email,
    })

    # Clear query params and force rerun
    st.query_params.clear()
    st.rerun()
