import streamlit as st
from utils.db import init_db, get_conn

st.set_page_config(page_title="Desk Booking", layout="wide")

# ---------------------------------------------------
# INIT DB
# ---------------------------------------------------
init_db()

# ---------------------------------------------------
# SESSION INITIALISATION
# ---------------------------------------------------
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", None)
st.session_state.setdefault("user_name", None)
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)

# ---------------------------------------------------
# AUTHENTICATION (CLOUD vs LOCAL)
# ---------------------------------------------------
if st.session_state.user_id is None:

    user = st.experimental_user  # Cloud provides email; Local usually does not

    # -----------------------------------------------
    # CASE 1 — RUNNING LOCALLY (NO AUTH AVAILABLE)
    # -----------------------------------------------
    if user is None or getattr(user, "email", None) is None:
        st.warning("Running in LOCAL DEVELOPMENT MODE — authentication bypassed.")
        fake_email = "localdev@richmondchambers.com"
        fake_name = "Local Developer"

        email = fake_email
        name = fake_name

    else:
        # -----------------------------------------------
        # CASE 2 — STREAMLIT CLOUD AUTHENTICATED USER
        # -----------------------------------------------
        email = user.email.lower()
        name = user.name or email.split("@")[0]

        # Domain restriction
        if not email.endswith("@richmondchambers.com"):
            st.error("Access restricted to Richmond Chambers users.")
            st.stop()

    # ---------------------------------------------------
    # DATABASE USER LOOKUP / CREATION
    # ---------------------------------------------------
    conn = get_conn()
    c = conn.cursor()

    row = c.execute(
        "SELECT id, name, role, can_book FROM users WHERE email=?",
        (email,),
    ).fetchone()

    if not row:
        c.execute(
            "INSERT INTO users (name, email, role, can_book) VALUES (?, ?, 'user', 1)",
            (name, email),
        )
        conn.commit()
        row = c.execute(
            "SELECT id, name, role, can_book FROM users WHERE email=?",
            (email,),
        ).fetchone()

    conn.close()

    # Save to session
    st.session_state.user_id = row[0]
    st.session_state.user_name = row[1]
    st.session_state.role = row[2]
    st.session_state.can_book = row[3]
    st.session_state.user_email = email

# ---------------------------------------------------
# SIDEBAR
# ---------------------------------------------------
st.sidebar.markdown(f"**User:** {st.session_state.user_name}")
st.sidebar.markdown(f"**Email:** {st.session_state.user_email}")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")

st.title("Desk Booking System")
st.write("Use the sidebar to navigate.")
