import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
from utils.audit import log_action
import json

# =====================================================
# PAGE TITLE
# =====================================================
st.title("Book a Desk")

# =====================================================
# SESSION SAFETY
# =====================================================
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", None)
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)
st.session_state.setdefault("selected_cells", [])

if st.session_state.user_id is None:
    st.error("User session not initialised.")
    st.stop()

if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

is_admin = st.session_state.role == "admin"

# =====================================================
# DATE PICKER
# =====================================================
selected_date = st.date_input("Select date", format="DD/MM/YYYY")
st.caption(f"Selected date: {selected_date.strftime('%d/%m/%Y')}")

if selected_date < date.today():
    st.error("Cannot book past dates.")
    st.stop()

if selected_date.weekday() >= 5:
    st.error("Desk booking is not available at weekends.")
    st.stop()

date_iso = selected_date.strftime("%Y-%m-%d")

# =====================================================
# LOAD DESKS (ENFORCED)
# =====================================================
conn = get_conn()

desks = conn.execute(
    """
    SELECT id, name
    FROM desks
    WHERE is_active = 1
      AND (
        admin_only = 0
        OR ? = 'admin'
      )
    ORDER BY name
    """,
    (st.session_state.role,),
).fetchall()

conn.close()

if not desks:
    st.warning("No desks are available for booking.")
    st.stop()

DESK_IDS = [d[0] for d in desks]
DESK_NAMES = {d[0]: d[1] for d in desks}

# =====================================================
# TIME SLOTS 09:00–18:00 (30 min)
# =====================================================
START = time(9, 0)
END = time(18, 0)
STEP = 30

def generate_slots():
    slots = []
    cur = datetime.combine(date.today(), START)
    end = datetime.combine(date.today(), END)
    while cur < end:
        slots.append(cur.time())
        cur += timedelta(minutes=STEP)
    return slots

SLOTS = generate_slots()

def is_past(t):
    if selected_date != date.today():
        return False
    return datetime.combine(date.today(), t) < datetime.now()

# =====================================================
# LOAD EXISTING BOOKINGS
# =====================================================
conn = get_conn()
rows = conn.execute(
    """
    SELECT b.desk_id, b.start_time, b.end_time, u.name, u.id
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE date = ? AND status='booked'
    """,
    (date_iso,),
).fetchall()
conn.close()

booked = {}
mine = set()

for desk_id, start, end, user_name, uid in rows:
    if desk_id not in DESK_IDS:
        continue

    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    for slot in SLOTS:
        if s <= slot < e:
            booked[(desk_id, slot)] = f"{user_name} ({start}–{end})"
            if uid == st.session_state.user_id:
                mine.add((desk_id, slot))

# =====================================================
# HEADER ROW
# =====================================================
header_html = "<div class='header-row'><div></div>"
for d in DESK_IDS:
    header_html += f"<div class='header-cell'>{DESK_NAMES[d]}</div>"
header_html += "</div>"
st.markdown(header_html, unsafe_allow_html=True)

# =====================================================
# JS PAYLOAD
# =====================================================
payload = {
    "desks": DESK_IDS,
    "times": [t.strftime("%H:%M") for t in SLOTS],
    "selected": st.session_state.selected_cells,
    "booked": [f"{d}_{t.strftime('%H:%M')}" for (d, t) in booked.keys()],
    "mine": [f"{d}_{t.strftime('%H:%M')}" for (d, t) in mine],
    "past": [
        f"{d}_{t.strftime('%H:%M')}"
        for d in DESK_IDS
        for t in SLOTS
        if is_past(t)
    ],
}

payload_json = json.dumps(payload)

# =====================================================
# HTML GRID (UNCHANGED)
# =====================================================
result = st.components.v1.html(
    f"""
    <script>
    const data = {payload_json};
    window.parent.postMessage(data, "*");
    </script>
    """,
    height=1,
)

# =====================================================
# RECEIVE SELECTION
# =====================================================
if isinstance(result, dict) and "selected" in result:
    st.session_state.selected_cells = result["selected"]

# =====================================================
# CONFIRM BOOKING (SERVER-SIDE ENFORCEMENT)
# =====================================================
if st.session_state.selected_cells:
    st.success(f"{len(st.session_state.selected_cells)} slot(s) selected.")

    if st.button("Confirm Booking"):
        conn = get_conn()
        c = conn.cursor()

        for key in st.session_state.selected_cells:
            desk_id, t = key.split("_")
            desk_id = int(desk_id)

            # ---- HARD ENFORCEMENT ----
            desk = c.execute(
                """
                SELECT is_active, admin_only
                FROM desks
                WHERE id=?
                """,
                (desk_id,),
            ).fetchone()

            if not desk or desk[0] == 0:
                conn.close()
                st.error("One or more selected desks are no longer available.")
                st.stop()

            if desk[1] == 1 and not is_admin:
                conn.close()
                st.error("You are not permitted to book one or more selected desks.")
                st.stop()

            start = t
            end_dt = datetime.combine(date.today(), time.fromisoformat(t)) + timedelta(minutes=30)
            end = end_dt.strftime("%H:%M")

            c.execute(
                """
                INSERT INTO bookings (user_id, desk_id, date, start_time, end_time, status)
                VALUES (?, ?, ?, ?, ?, 'booked')
                """,
                (st.session_state.user_id, desk_id, date_iso, start, end),
            )

        conn.commit()
        conn.close()

        log_action(
            action="NEW_BOOKING",
            details=f"{len(st.session_state.selected_cells)} slots booked on {date_iso}",
        )

        st.session_state.selected_cells = []
        st.success("Booking confirmed.")
        st.rerun()
