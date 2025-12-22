import streamlit as st
from google_auth_oauthlib.flow import Flow

def require_login():
    # Already authenticated
    if "oauth_email" in st.session_state:
        return

    # If a login is already in progress, do NOT regenerate state
    if "oauth_state" in st.session_state:
        st.title("Desk Booking System")
        st.info("Redirecting to Google sign-in…")
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
        redirect_uri=st.secrets["oauth"]["redirect_uri"],
    )

    auth_url, state = flow.authorization_url(
        prompt="consent",
        hd=st.secrets["oauth"]["allowed_domain"],
    )

    # Persist state ONCE
    st.session_state["oauth_state"] = state

    st.title("Desk Booking System")
    st.markdown("### Sign in required")
    st.markdown(
        f'<a href="{auth_url}">Sign in with Google</a>',
        unsafe_allow_html=True,
    )
    st.stop()
