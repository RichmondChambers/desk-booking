import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, date, time, timedelta
from pathlib import Path

import streamlit.components.v1 as components

from utils.db import ensure_db, get_conn
from utils.auth import require_login
from utils.styles import apply_lato_font

# --------------------------------------------------
# STREAMLIT COMPONENT DECLARATION
# --------------------------------------------------
component_root = Path(__file__).resolve().parent.parent / "desk_booking_component"
if not component_root.exists():
    component_root = Path(__file__).resolve().parent / "desk_booking_component"

desk_booking_component = components.declare_component(
    "desk_booking_component",
    path=str(component_root),
)

def desk_booking_grid(payload, height=520):
    return desk_booking_component(data=payload, height=height)

# --------------------------------------------------
# PAGE SETUP
# --------------------------------------------------
st.set_page_config(page_title="Book a Desk", layout="wide")
apply_lato_font()
st.title("Book a Desk")

# --------------------------------------------------
# AUTH & PERMISSION CHECK
# --------------------------------------------------
require_login()
ensure_db()

user_id = st.session_state.get("user_id")
can_book = st.session_state.get("can_book", 0)

if not user_id or not can_book:
    st.error("You do not have permission to book desks.")
    st.stop()

# --------------------------------------------------
# DATE PICKER
# --------------------------------------------------
selected_date = st.date_input("Select date", format="DD/MM/YYYY")

if selected_date.weekday() >= 5:
    st.warning("Desk booking is not available at weekends.")
    st.stop()

date_iso = selected_date.strftime("%Y-%m-%d")

# --------------------------------------------------
# LOAD DESKS
# --------------------------------------------------
conn = get_conn()

desks = conn.execute(
    """
    SELECT id, name
    FROM desks
    WHERE is_active = 1
    ORDER BY id
    """
).fetchall()

if not desks:
    conn.close()
    st.error("No desks available.")
    st.stop()

DESK_IDS = [row["id"] for row in desks]
DESK_NAMES = {row["id"]: row["name"] for row in desks}

# --------------------------------------------------
# TIME SLOTS (09:00 → 18:00)
# --------------------------------------------------
START = time(9, 0)
END = time(18, 0)
STEP = 30

slots = []
cur = datetime.combine(selected_date, START)
end_dt = datetime.combine(selected_date, END)

while cur < end_dt:
    slots.append(cur.time())
    cur += timedelta(minutes=STEP)

def is_past(t: time) -> bool:
    return (
        selected_date == date.today()
        and datetime.combine(selected_date, t) < datetime.now()
    )

# --------------------------------------------------
# LOAD BOOKINGS
# --------------------------------------------------
rows = conn.execute(
    """
    SELECT desk_id, start_time, end_time
    FROM bookings
    WHERE date = ?
      AND status = 'booked'
    """,
    (date_iso,),
).fetchall()

booked = set()

for row in rows:
    s = time.fromisoformat(row["start_time"])
    e = time.fromisoformat(row["end_time"])
    for t in slots:
        if s <= t < e:
            booked.add(f"{row['desk_id']}_{t.strftime('%H:%M')}")

conn.close()

# --------------------------------------------------
# GRID PAYLOAD
# --------------------------------------------------
payload = {
    "desks": DESK_IDS,
    "deskNames": DESK_NAMES,
    "times": [t.strftime("%H:%M") for t in slots],
    "booked": list(booked),
    "past": [
        f"{d}_{t.strftime('%H:%M')}"
        for d in DESK_IDS
        for t in slots
        if is_past(t)
    ],
    "dateLabel": selected_date.strftime("%d/%m/%Y"),
}

# --------------------------------------------------
# RENDER GRID
# --------------------------------------------------
selected_cells = desk_booking_grid(payload) or []

# --------------------------------------------------
# CONFIRM BOOKING
# --------------------------------------------------
st.divider()
st.subheader("Confirm booking")

if st.button("Confirm booking", type="primary", use_container_width=True):

    if not selected_cells:
        st.warning("Please select one or more time slots.")
        st.stop()

    by_desk = {}
    for cell in selected_cells:
        desk_id, t = cell.split("_")
        by_desk.setdefault(int(desk_id), []).append(time.fromisoformat(t))

    conn = get_conn()

    for desk_id, times in by_desk.items():
        times.sort()

        # Ensure contiguous time slots
        for a, b in zip(times, times[1:]):
            if (
                datetime.combine(selected_date, b)
                - datetime.combine(selected_date, a)
            ) != timedelta(minutes=STEP):
                conn.close()
                st.error("Selected time slots must be continuous.")
                st.stop()

        if any(is_past(t) for t in times):
            conn.close()
            st.error("Cannot book time slots in the past.")
            st.stop()

        start = times[0]
        end = (
            datetime.combine(selected_date, times[-1])
            + timedelta(minutes=STEP)
        ).time()

        conflict = conn.execute(
            """
            SELECT 1
            FROM bookings
            WHERE desk_id = ?
              AND date = ?
              AND status = 'booked'
              AND start_time < ?
              AND end_time > ?
            """,
            (desk_id, date_iso, end.isoformat(), start.isoformat()),
        ).fetchone()

        if conflict:
            conn.close()
            st.error("One or more selected slots are already booked.")
            st.stop()

        conn.execute(
            """
            INSERT INTO bookings
            (user_id, desk_id, date, start_time, end_time, status, checked_in)
            VALUES (?, ?, ?, ?, ?, 'booked', 0)
            """,
            (user_id, desk_id, date_iso, start.isoformat(), end.isoformat()),
        )

    conn.commit()
    conn.close()

    st.success("Booking confirmed.")
    st.rerun()
