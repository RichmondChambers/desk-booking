import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn


# =====================================================
# PAGE SETUP
# =====================================================
st.title("Book a Desk")


# =====================================================
# SESSION SAFETY
# =====================================================
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", "internal.user@richmondchambers.com")
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)

if st.session_state.user_id is None:
    st.error("User session not initialised. Please begin at the home page.")
    st.stop()

if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

is_admin = st.session_state.role == "admin"


# =====================================================
# DATE SELECTION — UK FORMAT
# =====================================================
selected_date = st.date_input("Select date", format="DD/MM/YYYY")
st.caption(f"Selected date: {selected_date.strftime('%d/%m/%Y')}")

if selected_date < date.today():
    st.error("Cannot book in the past.")
    st.stop()

if selected_date.weekday() >= 5:
    st.error("Cannot book on weekends.")
    st.stop()

date_iso = selected_date.strftime("%Y-%m-%d")


# =====================================================
# TIME SLOTS — 09:00 to 18:00, 30-min intervals
# =====================================================
START = time(9, 0)
END = time(18, 0)
SLOT_MINUTES = 30
DESKS = list(range(1, 16))

def generate_slots():
    slots = []
    now = datetime.combine(date.today(), START)
    end = datetime.combine(date.today(), END)
    while now < end:
        slots.append(now.time())
        now += timedelta(minutes=SLOT_MINUTES)
    return slots

SLOTS = generate_slots()


def is_past(slot):
    """Disable earlier slots if booking for today."""
    if selected_date != date.today():
        return False
    return datetime.combine(date.today(), slot) < datetime.now()


# =====================================================
# LOAD BOOKINGS FOR SELECTED DATE
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
own_slots = set()

for desk, start, end, user_name, user_id in rows:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)

    for slot in SLOTS:
        if s <= slot < e:
            booked[(desk, slot)] = f"{user_name} ({start}–{end})"
            if user_id == st.session_state.user_id:
                own_slots.add((desk, slot))


# =====================================================
# CSS (Restores the “nice look”)
# =====================================================
st.markdown("""
<style>

.header-row {
    display: grid;
    grid-template-columns: 90px repeat(15, 1fr);
    margin-top: 25px;
    margin-bottom: 10px;
    text-align: center;
    color: #e5e7eb;
    font-size: 16px;
    font-weight: 600;
    letter-spacing: .3px;
}

.header-cell {
    padding: 8px 0;
    border-bottom: 1px solid rgba(255,255,255,0.12);
}

.grid {
    display: grid;
    grid-template-columns: 90px repeat(15, 1fr);
    gap: 14px;
}

.time {
    color: #e5e7eb;
    font-size: 18px;
    font-weight: 600;
}

.cell {
    height: 42px;
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.10);
}

/* Available */
.available {
    background: rgba(31,41,55,0.55);
    transition: background .12s ease, border-color .12s ease;
}
.available:hover {
    background: rgba(55,65,81,0.65);
    border-color: rgba(255,255,255,0.25);
}

/* Already booked */
.booked {
    background: rgba(20,83,45,0.55);
    border-color: rgba(34,197,94,0.25);
}

/* User's own booking */
.own {
    background: rgba(30,58,74,0.75);
    border-color: rgba(59,130,246,0.35);
}

/* Past slots */
.past {
    background: rgba(31,41,55,0.25);
    border-color: rgba(255,255,255,0.05);
}

.legend {
    display:flex;
    gap: 14px;
    margin-top: 15px;
    margin-bottom: 10px;
    color: #cbd5e1;
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
""", unsafe_allow_html=True)



# =====================================================
# LEGEND
# =====================================================
st.markdown("""
<div class="legend">
  <span><span class="dot" style="background:rgba(31,41,55,0.70);"></span>Available</span>
  <span><span class="dot" style="background:rgba(20,83,45,0.70);"></span>Booked</span>
  <span><span class="dot" style="background:rgba(30,58,74,0.85);"></span>Your booking</span>
  <span><span class="dot" style="background:rgba(31,41,55,0.25);"></span>Past slot</span>
</div>
""", unsafe_allow_html=True)



# =====================================================
# HEADER ROW (Now Beautiful)
# =====================================================
header_html = "<div class='header-row'><div></div>"
for d in DESKS:
    header_html += f"<div class='header-cell'>Desk {d}</div>"
header_html += "</div>"

st.markdown(header_html, unsafe_allow_html=True)


# =====================================================
# GRID RENDERING (view-only)
# =====================================================
html = "<div class='grid'>"

for slot in SLOTS:

    # Time label
    html += f"<div class='time'>{slot.strftime('%H:%M')}</div>"

    for desk in DESKS:

        key = (desk, slot)
        tooltip = booked.get(key, "Available")

        # Determine cell class
        if key in own_slots:
            css = "cell own"
        elif key in booked:
            css = "cell booked"
        elif is_past(slot):
            css = "cell past"
        else:
            css = "cell available"

        html += f"<div class='{css}' title='{tooltip}'></div>"

html += "</div>"

st.markdown(html, unsafe_allow_html=True)


# =====================================================
# ADMIN NOTICE
# =====================================================
if is_admin:
    st.caption("Admin mode: override options will be added later.")
