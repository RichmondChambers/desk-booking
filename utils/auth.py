import streamlit as st
from urllib.parse import urlencode


def require_login():
    """
    Redirect the current tab to Google OAuth if the user is not authenticated.
    """
    if "oauth_email" in st.session_state:
        return

    params = {
        "client_id": st.secrets["oauth"]["client_id"],
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": st.secrets["oauth"]["redirect_uri"],
        "access_type": "online",
        "prompt": "select_account",
    }

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)

    st.title("Desk Booking System")
    st.markdown("### Redirecting to Google sign-in…")
    st.caption(
        "Google sign-in may open in a new tab due to browser security rules."
    )

    # Force top-level navigation (no clickable links, no popups)
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url={auth_url}">',
        unsafe_allow_html=True,
    )

    st.stop()


def require_admin():
    """
    Stop execution unless the current user is an admin.
    Assumes role has already been set in st.session_state by app.py.
    """
    if st.session_state.get("role") != "admin":
        st.error("Admins only.")
        st.stop()
