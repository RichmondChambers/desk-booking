import streamlit as st


def apply_lato_font() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Lato:wght@300;400;600;700&display=swap');

        html, body, [class*="css"] {
          font-family: 'Lato', sans-serif;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
