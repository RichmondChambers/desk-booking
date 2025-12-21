import streamlit as st

st.title("Office Map")

st.write("Visual representation of the 15-desk layout.")

# SIMPLE MAP GRID (placeholder)
cols = st.columns(5)

desk_no = 1
for i in range(3):  # 3 rows of 5 desks
    for j in range(5):
        cols[j].button(f"Desk {desk_no}", key=f"desk_{desk_no}")
        desk_no += 1

st.info("Click desks to view booking availability on the 'Book a Desk' page.")
