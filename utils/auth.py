import streamlit as st
from urllib.parse import urlencode

def require_login():
    # Already authenticated
    if "oauth_email" in st.session_state:
        return

    allowed = (st.secrets["oauth"].get("allowed_domain") or "").lower().strip()
    allowed = allowed.lstrip("@")  # allow either "@domain.com" or "domain.com"

    params = {
        "client_id": st.secrets["oauth"]["client_id"],
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": st.secrets["oauth"]["redirect_uri"],
        "access_type": "online",
        "prompt": "select_account",
    }

    # Only include hd hint if configured
    if allowed:
        params["hd"] = allowed

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)

    st.title("Desk Booking System")
    st.markdown("### Redirecting to Google sign-in…")
    st.caption(
        "Note: Google sign-in may open in a new tab due to browser security rules."
    )

    # Redirect (top-level navigation). This avoids clickable links that often open new tabs.
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url={auth_url}">',
        unsafe_allow_html=True,
    )

    st.stop()


def require_admin():
    """
    Stop the page unless the current session user is an admin.
    Assumes app.py has already mapped the OAuth user to a local user record and set:
      - st.session_state["role"]
      - st.session_state["user_email"]
    """
    role = st.session_state.get("role")
    if role != "admin":
        st.error("Admins only.")
        st.stop()
