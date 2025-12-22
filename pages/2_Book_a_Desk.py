import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
from utils.audit import audit_log

st.title("Book a Desk")

# ---------------------------------------------------
# SESSION STATE SAFETY
# ---------------------------------------------------
st.session_state.setdefault("selection", [])
st.session_state.setdefault("selected_desk", None)

# ---------------------------------------------------
# VALIDATE SESSION
# ---------------------------------------------------
if st.session_state.user_id is None:
    st.info("Loading user session…")
    st.stop()

if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

# ---------------------------------------------------
# DATE SELECTION (UK FORMAT)
# ---------------------------------------------------
selected_date = st.date_input(
    "Select date",
    format="DD/MM/YYYY"
)

# Disable weekends
if selected_date.weekday() >= 5:
    st.warning("Desk booking is not available on weekends.")
    st.stop()

# ---------------------------------------------------
# TIME SLOTS (09:00–18:00)
# ---------------------------------------------------
START = time(9, 0)
END = time(18, 0)
SLOT_MINUTES = 30

def generate_slots():
    slots = []
    current = datetime.combine(date.today(), START)
    end = datetime.combine(date.today(), END)
    while current < end:
        slots.append(current.time())
        current += timedelta(minutes=SLOT_MINUTES)
    return slots

time_slots = generate_slots()
desks = range(1, 16)

# ---------------------------------------------------
# LOAD BOOKINGS
# ---------------------------------------------------
conn = get_conn()
c = conn.cursor()

bookings = c.execute(
    """
    SELECT desk_id, start_time, end_time, user_id
    FROM bookings
    WHERE date=? AND status='booked'
    """,
    (selected_date.strftime("%Y-%m-%d"),),
).fetchall()

conn.close()

occupied = {}
for desk_id, start, end, uid in bookings:
    occupied.setdefault(desk_id, []).append((start, end, uid))

# ---------------------------------------------------
# GRID STYLES
# ---------------------------------------------------
st.markdown("""
<style>
.grid { display: grid; grid-template-columns: 80px repeat(15, 1fr); gap: 6px; }
.cell {
    height: 32px;
    border-radius: 6px;
    background: #1f2937;
    border: 1px solid #374151;
}
.available:hover { background: #2563eb; cursor: pointer; }
.booked { background: #14532d; }
.mine { background: #1d4ed8; }
.selected { outline: 2px solid #3b82f6; }
.time { color: #9ca3af; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------
# GRID RENDER
# ---------------------------------------------------
st.subheader("Select desk and time range")

st.markdown('<div class="grid">', unsafe_allow_html=True)
st.markdown("<div></div>", unsafe_allow_html=True)

for d in desks:
    st.markdown(f"<strong>Desk {d}</strong>", unsafe_allow_html=True)

now = datetime.now()

for t in time_slots:
    st.markdown(f"<div class='time'>{t.strftime('%H:%M')}</div>", unsafe_allow_html=True)

    for d in desks:
        slot_dt = datetime.combine(selected_date, t)
        disabled = selected_date == date.today() and slot_dt <= now

        booked_by = None
        for s, e, uid in occupied.get(d, []):
            if s <= t.strftime("%H:%M") < e:
                booked_by = uid

        css = "cell"
        if booked_by:
            css += " mine" if booked_by == st.session_state.user_id else " booked"
        elif disabled:
            css += ""
        else:
            css += " available"

        key = f"{d}_{t}"

        if not booked_by and not disabled:
            if st.button("", key=key):
                st.session_state.selected_desk = d
                st.session_state.selection = [t]
        st.markdown(f"<div class='{css}'></div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------
# CONFIRM BOOKING
# ---------------------------------------------------
if st.session_state.selection:
    st.success(
        f"Selected Desk {st.session_state.selected_desk} at "
        f"{st.session_state.selection[0].strftime('%H:%M')}"
    )

    if st.button("Confirm Booking"):
        conn = get_conn()
        c = conn.cursor()

        c.execute(
            """
            INSERT INTO bookings
            (user_id, desk_id, date, start_time, end_time, status)
            VALUES (?, ?, ?, ?, ?, 'booked')
            """,
            (
                st.session_state.user_id,
                st.session_state.selected_desk,
                selected_date.strftime("%Y-%m-%d"),
                st.session_state.selection[0].strftime("%H:%M"),
                (datetime.combine(date.today(), st.session_state.selection[0]) + timedelta(minutes=30)).time().strftime("%H:%M"),
            ),
        )

        conn.commit()
        conn.close()

        audit_log(
            st.session_state.user_email,
            "NEW_BOOKING",
            f"desk={st.session_state.selected_desk}"
        )

        st.success("Booking confirmed.")
        st.session_state.selection = []
        st.rerun()
