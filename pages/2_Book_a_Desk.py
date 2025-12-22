import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
from utils.audit import log_action
import json

st.title("Book a Desk")

# --------------------------------------------------
# SESSION SAFETY
# --------------------------------------------------
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

# --------------------------------------------------
# DATE PICKER
# --------------------------------------------------
selected_date = st.date_input("Select date", format="DD/MM/YYYY")
st.caption(f"Selected date: {selected_date.strftime('%d/%m/%Y')}")

if selected_date < date.today():
    st.error("Cannot book past dates.")
    st.stop()

if selected_date.weekday() >= 5:
    st.error("Desk booking is not available at weekends.")
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
      AND (admin_only = 0 OR ? = 'admin')
    ORDER BY id
    """,
    (st.session_state.role,),
).fetchall()
conn.close()

if not desks:
    st.warning("No desks available.")
    st.stop()

DESK_IDS = [d[0] for d in desks]
DESK_NAMES = {d[0]: d[1] for d in desks}

# --------------------------------------------------
# TIME SLOTS (09:00 → 18:00 INCLUSIVE)
# --------------------------------------------------
START = time(9, 0)
END = time(18, 0)
STEP = 30

slots = []
cur = datetime.combine(date.today(), START)
end_dt = datetime.combine(date.today(), END)
while cur <= end_dt:
    slots.append(cur.time())
    cur += timedelta(minutes=STEP)

def is_past(t):
    if selected_date != date.today():
        return False
    return datetime.combine(date.today(), t) < datetime.now()

# --------------------------------------------------
# LOAD BOOKINGS
# --------------------------------------------------
conn = get_conn()
rows = conn.execute(
    """
    SELECT b.desk_id, b.start_time, b.end_time, u.name, u.id
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE date=? AND status='booked'
    """,
    (date_iso,),
).fetchall()
conn.close()

booked = {}
mine = set()

for desk_id, start, end, user_name, uid in rows:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    for t in slots:
        if s <= t < e:
            key = f"{desk_id}_{t.strftime('%H:%M')}"
            booked[key] = user_name
            if uid == st.session_state.user_id:
                mine.add(key)

# --------------------------------------------------
# INLINE LEGEND
# --------------------------------------------------
st.markdown("""
<div style="display:flex; gap:24px; margin-bottom:12px; font-size:14px;">
  <div style="color:#fff;">⬜ Available</div>
  <div style="color:#009fdf;">■ Your booking</div>
  <div style="color:#c0392b;">■ Booked</div>
  <div style="color:#555;">■ Past</div>
</div>
""", unsafe_allow_html=True)

# --------------------------------------------------
# GRID HTML + JS (FULLY INTERACTIVE)
# --------------------------------------------------
payload = {
    "desks": DESK_IDS,
    "deskNames": DESK_NAMES,
    "times": [t.strftime("%H:%M") for t in slots],
    "selected": st.session_state.selected_cells,
    "booked": booked,
    "mine": list(mine),
    "past": [
        f"{d}_{t.strftime('%H:%M')}"
        for d in DESK_IDS
        for t in slots
        if is_past(t)
    ],
}

html = f"""
<style>
.grid {{
  display: grid;
  grid-template-columns: 90px repeat({len(DESK_IDS)}, 1fr);
  gap: 12px;
}}

.time {{
  color: #e5e7eb;
  font-weight: 600;
}}

.header {{
  color: #e5e7eb;
  font-weight: 700;
  text-align: center;
}}

.cell {{
  height: 42px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.25);
}}

.available {{
  background: #ffffff;
  cursor: pointer;
}}

.available:hover {{
  outline: 2px solid #009fdf;
}}

.selected {{
  background: #009fdf !important;
}}

.own {{
  background: #009fdf;
  cursor: not-allowed;
}}

.booked {{
  background: #c0392b;
  cursor: not-allowed;
}}

.past {{
  background: #2c2c2c;
  cursor: not-allowed;
}}
</style>

<div class="grid" id="grid"></div>

<script>
const data = {json.dumps(payload)};
const grid = document.getElementById("grid");

let selected = new Set(data.selected);
let dragging = false;

// Header row
grid.appendChild(document.createElement("div"));
data.desks.forEach(d => {{
  const h = document.createElement("div");
  h.className = "header";
  h.innerText = data.deskNames[d];
  grid.appendChild(h);
}});

// Build rows
data.times.forEach(time => {{
  const t = document.createElement("div");
  t.className = "time";
  t.innerText = time;
  grid.appendChild(t);

  data.desks.forEach(desk => {{
    const key = desk + "_" + time;
    const c = document.createElement("div");

    if (data.mine.includes(key)) c.className = "cell own";
    else if (data.booked[key]) {{
      c.className = "cell booked";
      c.title = "Booked by " + data.booked[key];
    }}
    else if (data.past.includes(key)) c.className = "cell past";
    else c.className = "cell available";

    if (selected.has(key)) c.classList.add("selected");

    c.onmousedown = () => {{
      if (!c.classList.contains("available")) return;
      dragging = true;
      toggle(key, c);
    }};
    c.onmouseover = () => {{
      if (dragging) toggle(key, c);
    }};
    c.onmouseup = () => dragging = false;

    grid.appendChild(c);
  }});
}});

document.onmouseup = () => dragging = false;

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
</script>
"""

result = st.components.v1.html(html, height=1000)

# --------------------------------------------------
# RECEIVE SELECTION
# --------------------------------------------------
if isinstance(result, dict) and "selected" in result:
    st.session_state.selected_cells = result["selected"]

# --------------------------------------------------
# BOOKING SUMMARY
# --------------------------------------------------
if st.session_state.selected_cells:
    st.markdown("### Booking Summary")
    st.write(f"{len(st.session_state.selected_cells)} slots selected")

    if st.button("Confirm booking"):
        conn = get_conn()
        c = conn.cursor()

        for key in st.session_state.selected_cells:
            desk_id, t = key.split("_")
            end = (
                datetime.combine(date.today(), time.fromisoformat(t))
                + timedelta(minutes=30)
            ).strftime("%H:%M")

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
            details=f"{len(st.session_state.selected_cells)} slots on {date_iso}",
        )

        st.session_state.selected_cells = []
        st.success("Booking confirmed.")
        st.rerun()
