import streamlit as st
from datetime import datetime, date, time, timedelta

from utils.db import ensure_db, get_conn
from utils.auth import require_login
from utils.styles import apply_lato_font, HEADER_STYLE


# --------------------------------------------------
# HELPERS
# --------------------------------------------------
STEP = 30
START = time(9, 0)
END = time(18, 0)

def generate_slots(selected_date: date):
    slots = []
    cur = datetime.combine(selected_date, START)
    end_dt = datetime.combine(selected_date, END)

    while cur < end_dt:
        slots.append(cur.time())
        cur += timedelta(minutes=STEP)

    return slots


def is_past_slot(selected_date: date, t: time, now: datetime) -> bool:
    return selected_date == date.today() and datetime.combine(selected_date, t) < now


def time_label(t: time) -> str:
    return t.strftime("%H:%M")


# --------------------------------------------------
# PAGE SETUP
# --------------------------------------------------
st.set_page_config(page_title="Book a Desk", layout="wide")
apply_lato_font()
st.title("Book a Desk")
st.markdown(HEADER_STYLE, unsafe_allow_html=True)

# --------------------------------------------------
# AUTH & DB
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
now = datetime.now()

# --------------------------------------------------
# LOAD DESKS
# --------------------------------------------------
with get_conn() as conn:
    desks = conn.execute(
        """
        SELECT id, name
        FROM desks
        WHERE is_active = 1
        ORDER BY id
        """
    ).fetchall()

if not desks:
    st.error("No desks available.")
    st.stop()

DESK_IDS = [row["id"] for row in desks]
DESK_NAMES = {row["id"]: row["name"] for row in desks}

# --------------------------------------------------
# TIME SLOTS
# --------------------------------------------------
slots = generate_slots(selected_date)

# --------------------------------------------------
# LOAD EXISTING BOOKINGS
# --------------------------------------------------
booked = {desk_id: set() for desk_id in DESK_IDS}

with get_conn() as conn:
    rows = conn.execute(
        """
        SELECT desk_id, start_time, end_time
        FROM bookings
        WHERE date = ?
          AND status = 'booked'
        """,
        (date_iso,),
    ).fetchall()

for row in rows:
    s = time.fromisoformat(row["start_time"])
    e = time.fromisoformat(row["end_time"])
    for t in slots:
        if s <= t < e:
            booked[row["desk_id"]].add(t)

# --------------------------------------------------
# RANGE SELECTION UI
# --------------------------------------------------
st.subheader("Select time range per desk")

selections = {}

for desk_id in DESK_IDS:
    st.markdown(f"### {DESK_NAMES[desk_id]}")

    available = [
        t for t in slots
        if t not in booked[desk_id]
        and not is_past_slot(selected_date, t, now)
    ]

    if not available:
        st.info("No available slots")
        continue

    labels = [time_label(t) for t in available]

    start_label = st.selectbox(
        "Start time",
        ["—"] + labels,
        key=f"start_{desk_id}_{selected_date}",
    )

    end_label = st.selectbox(
        "End time",
        ["—"] + labels,
        key=f"end_{desk_id}_{selected_date}",
    )

    if start_label != "—" and end_label != "—":
        start = time.fromisoformat(start_label)
        end = time.fromisoformat(end_label)

        if end <= start:
            st.error("End time must be after start time.")
        else:
            selections[desk_id] = (start, end)

# --------------------------------------------------
# CONFIRM BOOKING
# --------------------------------------------------
st.divider()

if st.button("Confirm booking", type="primary", use_container_width=True):

    if not selections:
        st.warning("Please select at least one booking.")
        st.stop()

    with get_conn() as conn:
        for desk_id, (start, end) in selections.items():

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
                st.error(f"{DESK_NAMES[desk_id]} has a conflicting booking.")
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

    st.success("Booking confirmed.")
    st.rerun()
