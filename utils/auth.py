import streamlit as st
from google_auth_oauthlib.flow import Flow


def require_login():
    # Already authenticated
    if "oauth_email" in st.session_state:
        return

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": st.secrets["oauth"]["client_id"],
                "client_secret": st.secrets["oauth"]["client_secret"],
                # Use v2 endpoint
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

    auth_url, _ = flow.authorization_url(
        prompt="select_account"
    )

    st.title("Desk Booking System")
    st.markdown("### Sign in required")

    # IMPORTANT: user-initiated navigation only
    st.link_button("Sign in with Google", auth_url)

    st.stop()


def require_admin():
    if st.session_state.get("role") != "admin":
        st.error("Admins only.")
        st.stop()
