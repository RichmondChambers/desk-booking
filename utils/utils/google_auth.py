import streamlit as st
import urllib.parse
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests

def settings():
    cfg = st.secrets["oauth"]
    return (
        cfg["client_id"],
        cfg["client_secret"],
        cfg["redirect_uri"],
        cfg["allowed_domain"]
    )

def google_login_link():
    client_id, client_secret, redirect_uri, allowed_domain = settings()

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=["openid", "email", "profile"]
    )

    flow.redirect_uri = redirect_uri

    auth_url, _ = flow.authorization_url(
        prompt="consent",
        include_granted_scopes="true"
    )

    st.markdown(f"[Sign in with Google]({auth_url})")

def handle_oauth_response():
    qp = st.query_params
    if "code" not in qp:
        return

    code = qp["code"]

    client_id, client_secret, redirect_uri, allowed_domain = settings()

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=["openid", "email", "profile"]
    )

    flow.redirect_uri = redirect_uri

    flow.fetch_token(code=code)

    credentials = flow.credentials
    request = requests.Request()
    info = id_token.verify_oauth2_token(
        credentials.id_token, request, client_id
    )

    email = info["email"]
    name = info.get("name", email.split("@")[0])

    if not email.endswith(f"@{allowed_domain}"):
        st.error("You must use a permitted Google Workspace account.")
        st.stop()

    st.session_state.user_email = email
    st.session_state.user_name = name
    st.session_state.user_id = email

    st.query_params.clear()
