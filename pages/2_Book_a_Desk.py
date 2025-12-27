import streamlit as st
from datetime import datetime, date, time, timedelta
import json

from utils.db import get_conn
from utils.auth import require_login

st.set_page_config(page_title="Book a Desk", layout="wide")
st.title("Book a Desk")

# --------------------------------------------------
# AUTH & PERMISSION CHECK
# --------------------------------------------------
require_login()

user_id = st.session_state.get("user_id")
can_book = st.session_state.get("can_book", 0)

if not user_id or not can_book:
    st.error("You do not have permission to book desks.")
    st.stop()

# --------------------------------------------------
# HIDDEN INPUT BRIDGE (FOR GRID SELECTION)
# --------------------------------------------------
selected_cells_str = st.text_input(
    "selected_cells_hidden",
    value="",
    key="selected_cells_hidden",
    label_visibility="collapsed",
)

selected_cells = (
    selected_cells_str.split(",") if selected_cells_str else []
)

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

DESK_IDS = [d["id"] for d in desks]
DESK_NAMES = {d["id"]: d["name"] for d in desks}

# --------------------------------------------------
# TIME SLOTS (09:00 → 18:00)
# --------------------------------------------------
START = time(9, 0)
END = time(18, 0)
STEP = 30

slots = []
cur = datetime.combine(selected_date, START)
end_dt = datetime.combine(selected_date, END)

while cur <= end_dt:
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
    WHERE date = ? AND status = 'booked'
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
# GRID RENDER
# --------------------------------------------------
html = """<your existing HTML/JS unchanged>""" % (
    len(DESK_IDS),
    json.dumps(payload),
)

st.components.v1.html(html, height=1200)

# --------------------------------------------------
# CONFIRM BOOKING
# --------------------------------------------------
st.divider()
st.subheader("Confirm booking")

if st.button("Confirm booking", type="primary"):
    if not selected_cells:
        st.warning("Please select a time slot.")
        st.stop()

    # Group & validate contiguity
    by_desk = {}
    for cell in selected_cells:
        desk_id, t = cell.split("_")
        by_desk.setdefault(int(desk_id), []).append(
            time.fromisoformat(t)
        )

    conn = get_conn()

    for desk_id, times in by_desk.items():
        times.sort()

        # Enforce contiguity
        for a, b in zip(times, times[1:]):
            if (
                datetime.combine(selected_date, b)
                - datetime.combine(selected_date, a)
            ) != timedelta(minutes=STEP):
                conn.close()
                st.error("Selected time slots must be continuous.")
                st.stop()

        # Enforce past-time protection
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
            (
                desk_id,
                date_iso,
                end.isoformat(),
                start.isoformat(),
            ),
        ).fetchone()

        if conflict:
            conn.close()
            st.error("One or more slots are already booked.")
            st.stop()

        conn.execute(
            """
            INSERT INTO bookings
            (user_id, desk_id, date, start_time, end_time, status, checked_in)
            VALUES (?, ?, ?, ?, ?, 'booked', 0)
            """,
            (
                user_id,
                desk_id,
                date_iso,
                start.isoformat(),
                end.isoformat(),
            ),
        )

    conn.commit()
    conn.close()

    st.success("Booking confirmed.")
    st.rerun()
