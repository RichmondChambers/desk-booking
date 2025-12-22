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
# LOAD DESKS
# =====================================================
conn = get_conn()
desks = conn.execute(
    """
    SELECT id, name
    FROM desks
    WHERE is_active = 1
      AND (admin_only = 0 OR ? = 'admin')
    ORDER BY id
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
# TIME SLOTS 09:00–18:00 (30 MIN)
# =====================================================
START = time(9, 0)
END = time(18, 0)
STEP = 30

def generate_slots():
    slots = []
    cur = datetime.combine(date.today(), START)
    end = datetime.combine(date.today(), END)
    while cur <= end:
        slots.append(cur.time())
        cur += timedelta(minutes=STEP)
    return slots

SLOTS = generate_slots()

def is_past(t):
    if selected_date != date.today():
        return False
    return datetime.combine(date.today(), t) < datetime.now()

# =====================================================
# LOAD BOOKINGS
# =====================================================
conn = get_conn()
rows = conn.execute(
    """
    SELECT b.desk_id, b.start_time, b.end_time, u.name, u.id
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE date = ? AND status = 'booked'
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
            booked[(desk_id, slot)] = user_name
            if uid == st.session_state.user_id:
                mine.add((desk_id, slot))

# =====================================================
# INLINE LEGEND (NO LABEL)
# =====================================================
st.markdown("""
<div style="display:flex; gap:20px; margin-bottom:15px;">
  <div>⬜ Available</div>
  <div style="color:#009fdf;">■ Your booking</div>
  <div style="color:#c0392b;">■ Booked</div>
  <div style="color:#555;">■ Past</div>
</div>
""", unsafe_allow_html=True)

# =====================================================
# GRID CSS
# =====================================================
st.markdown("""
<style>
.grid {
    display: grid;
    grid-template-columns: 90px repeat(auto-fit, minmax(160px, 1fr));
    gap: 10px;
    align-items: center;
}
.time {
    font-weight: 600;
    opacity: 0.8;
}
.cell {
    height: 44px;
    border-radius: 10px;
    border: 1px solid #ccc;
    cursor: pointer;
}
.available { background: #ffffff; }
.own { background: #009fdf; color: white; cursor: not-allowed; }
.booked { background: #c0392b; color: white; cursor: not-allowed; }
.past { background: #2c2c2c; cursor: not-allowed; }
.selected { outline: 3px solid #009fdf; }
</style>
""", unsafe_allow_html=True)

# =====================================================
# BUILD JS GRID
# =====================================================
payload = {
    "desks": DESK_IDS,
    "desk_names": DESK_NAMES,
    "times": [t.strftime("%H:%M") for t in SLOTS],
    "selected": st.session_state.selected_cells,
    "booked": {f"{d}_{t.strftime('%H:%M')}": booked[(d, t)] for (d, t) in booked},
    "mine": [f"{d}_{t.strftime('%H:%M')}" for (d, t) in mine],
    "past": [f"{d}_{t.strftime('%H:%M')}" for d in DESK_IDS for t in SLOTS if is_past(t)],
}

html = f"""
<div class="grid" id="grid"></div>

<script>
const data = {json.dumps(payload)};
const grid = document.getElementById("grid");

let selected = new Set(data.selected);
let dragging = false;

function cellClass(key) {{
  if (data.mine.includes(key)) return "cell own";
  if (data.booked[key]) return "cell booked";
  if (data.past.includes(key)) return "cell past";
  return "cell available";
}}

function toggle(key, el) {{
  if (!el.classList.contains("available")) return;
  if (selected.has(key)) {{
    selected.delete(key);
    el.classList.remove("selected");
  }} else {{
    selected.add(key);
    el.classList.add("selected");
  }}
  window.parent.postMessage({{selected: Array.from(selected)}}, "*");
}}

Object.values(data.times).forEach(time => {{
  const t = document.createElement("div");
  t.className = "time";
  t.innerText = time;
  grid.appendChild(t);

  data.desks.forEach(desk => {{
    const key = desk + "_" + time;
    const el = document.createElement("div");
    el.className = cellClass(key);
    el.title = data.booked[key] ? "Booked by " + data.booked[key] : "";

    if (selected.has(key)) el.classList.add("selected");

    el.onmousedown = () => {{ dragging = true; toggle(key, el); }};
    el.onmouseover = () => {{ if (dragging) toggle(key, el); }};
    el.onmouseup = () => dragging = false;

    grid.appendChild(el);
  }});
}});

document.onmouseup = () => dragging = false;
</script>
"""

result = st.components.v1.html(html, height=900)

# =====================================================
# RECEIVE SELECTION
# =====================================================
if isinstance(result, dict) and "selected" in result:
    st.session_state.selected_cells = result["selected"]

# =====================================================
# BOOKING SUMMARY + CONFIRM
# =====================================================
if st.session_state.selected_cells:
    st.markdown("### Booking Summary")

    slots = sorted(st.session_state.selected_cells)
    st.write(f"**{len(slots)} slots selected**")

    if st.button("Confirm booking"):
        conn = get_conn()
        c = conn.cursor()

        for key in slots:
            desk_id, t = key.split("_")
            end = (datetime.combine(date.today(), time.fromisoformat(t)) + timedelta(minutes=30)).strftime("%H:%M")

            c.execute(
                """
                INSERT INTO bookings (user_id, desk_id, date, start_time, end_time, status)
                VALUES (?, ?, ?, ?, ?, 'booked')
                """,
                (st.session_state.user_id, int(desk_id), date_iso, t, end),
            )

        conn.commit()
        conn.close()

        log_action(
            action="NEW_BOOKING",
            details=f"{len(slots)} slots booked on {date_iso}",
        )

        st.session_state.selected_cells = []
        st.success("Booking confirmed.")
        st.rerun()
