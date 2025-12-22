import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn

# =====================================================
# PAGE SETUP
# =====================================================
st.title("Book a Desk")

# =====================================================
# SESSION SAFETY (do NOT re-auth here; trust app.py)
# =====================================================
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", "internal.user@richmondchambers.com")
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)

if st.session_state.user_id is None:
    st.error("User session not initialised. Please start from the home page.")
    st.stop()

if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

is_admin = st.session_state.role == "admin"

# =====================================================
# DATE SELECTION (UK FORMAT)
# =====================================================
date_choice = st.date_input("Select date", format="DD/MM/YYYY")
st.caption(f"Selected date: {date_choice.strftime('%d/%m/%Y')}")

if date_choice < date.today():
    st.error("Bookings cannot be made for past dates.")
    st.stop()

if date_choice.weekday() >= 5:
    st.error("Bookings cannot be made on weekends.")
    st.stop()

date_iso = date_choice.strftime("%Y-%m-%d")

# =====================================================
# GRID CONFIG (09:00–18:00)
# =====================================================
START_HOUR = 9
END_HOUR = 18
SLOT_MINUTES = 30
DESKS = list(range(1, 16))

def generate_slots():
    slots = []
    current = datetime.combine(date.today(), time(START_HOUR))
    end = datetime.combine(date.today(), time(END_HOUR))
    while current < end:
        slots.append(current.time())
        current += timedelta(minutes=SLOT_MINUTES)
    return slots

SLOTS = generate_slots()

def is_past(slot):
    if date_choice != date.today():
        return False
    return datetime.combine(date.today(), slot) < datetime.now()

# =====================================================
# LOAD BOOKINGS FOR THIS DAY
# =====================================================
conn = get_conn()
c = conn.cursor()

rows = c.execute(
    """
    SELECT b.desk_id, b.start_time, b.end_time, u.name, u.id
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE b.date = ?
      AND b.status = 'booked'
    """,
    (date_iso,),
).fetchall()

conn.close()

booked = {}
own = set()

for desk, start, end, name, uid in rows:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    for slot in SLOTS:
        if s <= slot < e:
            booked[(desk, slot)] = f"{name} ({start}–{end})"
            if uid == st.session_state.user_id:
                own.add((desk, slot))

# =====================================================
# CSS (the “nice look”)
# =====================================================
st.markdown(
    """
<style>
.grid {
  display: grid;
  grid-template-columns: 90px repeat(15, 1fr);
  gap: 14px;
  align-items: center;
  margin-top: 10px;
}

.header {
  font-weight: 600;
  text-align: center;
  color: #e5e7eb;
  font-size: 16px;
}

.time {
  color: #e5e7eb;
  font-size: 18px;
  font-weight: 600;
}

.cell {
  height: 42px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.15);
  background: rgba(17,24,39,0.55);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.03);
}

.available {
  background: rgba(31,41,55,0.55);
  transition: transform .08s ease, border-color .12s ease, background .12s ease;
}

.available:hover {
  border-color: rgba(255,255,255,0.30);
  transform: translateY(-1px);
}

.booked {
  background: rgba(20,83,45,0.55);
  border-color: rgba(34,197,94,0.25);
}

.own {
  background: rgba(30,58,74,0.65);
  border-color: rgba(59,130,246,0.25);
}

.past {
  background: rgba(31,41,55,0.25);
  border-color: rgba(255,255,255,0.08);
}

.legend {
  display:flex;
  gap:14px;
  margin: 10px 0 0 0;
  color:#cbd5e1;
  font-size: 14px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display:inline-block;
  margin-right: 6px;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="legend">
  <span><span class="dot" style="background:rgba(31,41,55,0.80);"></span>Available</span>
  <span><span class="dot" style="background:rgba(20,83,45,0.80);"></span>Booked</span>
  <span><span class="dot" style="background:rgba(30,58,74,0.85);"></span>My booking</span>
  <span><span class="dot" style="background:rgba(31,41,55,0.35);"></span>Past slot</span>
</div>
""",
    unsafe_allow_html=True,
)

# =====================================================
# RENDER GRID (VIEW-ONLY rollback)
# =====================================================
st.subheader("Select desk and time range")

html = "<div class='grid'>"
html += "<div></div>"
for d in DESKS:
    html += f"<div class='header'>Desk {d}</div>"

for slot in SLOTS:
    html += f"<div class='time'>{slot.strftime('%H:%M')}</div>"

    for desk in DESKS:
        key = (desk, slot)
        tooltip = booked.get(key, "Available")

        if key in own:
            css = "cell own"
        elif key in booked:
            css = "cell booked"
        elif is_past(slot):
            css = "cell past"
        else:
            css = "cell available"

        # View-only cell with tooltip (keeps the look)
        html += f"<div class='{css}' title='{tooltip}'></div>"

html += "</div>"
st.markdown(html, unsafe_allow_html=True)

if is_admin:
    st.caption("Admin: override controls are not enabled in this rollback view.")
