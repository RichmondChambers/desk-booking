import streamlit as st
from urllib.parse import urlencode

def require_login():
    # Already authenticated
    if "oauth_email" in st.session_state:
        return

    params = {
        "client_id": st.secrets["oauth"]["client_id"],
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": st.secrets["oauth"]["redirect_uri"],
        "access_type": "online",
        "prompt": "select_account",
        "hd": st.secrets["oauth"]["allowed_domain"],
    }

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode(params)
    )

    st.title("Desk Booking System")
    st.markdown("### Redirecting to Google sign-in…")

    # 🔑 SAME-TAB REDIRECT — NO NEW WINDOW
    st.markdown(
        f"""
        <meta http-equiv="refresh" content="0; url={auth_url}">
        """,
        unsafe_allow_html=True,
    )

    st.stop()
