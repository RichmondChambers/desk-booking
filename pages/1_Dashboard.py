import streamlit as st


# ---------------------------------------------------
# PAGE SETUP
# ---------------------------------------------------
st.title("Dashboard")
st.subheader("Your Profile")


# ---------------------------------------------------
# SESSION STATE SAFETY
# ---------------------------------------------------
st.session_state.setdefault("user_name", "Internal User")
st.session_state.setdefault("user_email", "internal.user@richmondchambers.com")
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)


# ---------------------------------------------------
# PROFILE DISPLAY
# ---------------------------------------------------
st.write(f"**Name:** {st.session_state.user_name}")
st.write(f"**Email:** {st.session_state.user_email}")
st.write(f"**Role:** {st.session_state.role}")

if not st.session_state.can_book:
    st.warning("You do not currently have permission to book desks.")
else:
    st.success("You are permitted to book desks.")
