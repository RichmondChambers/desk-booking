import streamlit as st

def require_admin():
    if st.session_state.get("role") != "admin":
        st.error("You do not have permission to access this page.")
        st.stop()

def require_can_book():
    if not st.session_state.get("can_book"):
        st.error("You are not permitted to make desk bookings.")
        st.stop()
