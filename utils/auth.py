import streamlit as st
from google_auth_oauthlib.flow import Flow
import streamlit.components.v1 as components

def require_login():
    if "oauth_email" in st.session_state:
        return

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

    auth_url, _ = flow.authorization_url()

    st.title("Desk Booking System")
    st.markdown("### Redirecting to Google sign-in…")

    # 🔑 BREAK OUT OF THE IFRAME (THIS IS THE FIX)
    components.html(
        f"""
        <script>
            window.top.location.href = "{auth_url}";
        </script>
        """,
        height=0,
    )

    st.stop()
