import streamlit as st

st.title("Office Map")

st.write("Optional: upload an office map image to assets/office_map.png")

try:
    st.image("assets/office_map.png", use_container_width=True)
except Exception:
    st.info("No office map image found.")
