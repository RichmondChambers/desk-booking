import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
from utils.audit import log_action
import json

st.set_page_config(page_title="Book a Desk", layout="wide")
st.title("Book a Desk")

# --------------------------------------------------
# PERMISSIONS
# --------------------------------------------------
if not st.session_state.get("user_id"):
    st.error("Not logged in.")
    st.stop()

if not st.session_state.get("can_book"):
    st.error("You are not permitted to make bookings.")
    st.stop()

# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
st.session_state.setdefault("selected_cells", [])

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
      AND (admin_only = 0 OR ? = 'admin')
    ORDER BY id
    """,
    (st.session_state.role,),
).fetchall()
conn.close()

DESK_IDS = [d[0] for d in desks]
DESK_NAMES = {d[0]: d[1] for d in desks}

# --------------------------------------------------
# TIME SLOTS
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

def is_past(t):
    return selected_date == date.today() and datetime.combine(selected_date, t) < datetime.now()

# --------------------------------------------------
# LOAD BOOKINGS
# --------------------------------------------------
conn = get_conn()
rows = conn.execute(
    """
    SELECT desk_id, start_time, end_time
    FROM bookings
    WHERE date = ? AND status = 'booked'
    """,
    (date_iso,),
).fetchall()
conn.close()

booked = set()
for desk_id, start, end in rows:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    for t in slots:
        if s <= t < e:
            booked.add(f"{desk_id}_{t.strftime('%H:%M')}")

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
# GRID UI (YOUR ORIGINAL HTML — FIXED)
# --------------------------------------------------
html = """
<style>
html, body { margin:0; padding:0; font-family:inherit; }
* { box-sizing:border-box; font-family:inherit; }

.grid { display:grid; grid-template-columns:90px repeat(%d,1fr); gap:12px; }
.time,.header { color:#e5e7eb; text-align:center; font-size:14px; }
.header { font-weight:600; }

.cell {
  height:42px;
  border-radius:10px;
  border:1px solid rgba(255,255,255,0.25);
}

.available { background:#ffffff; cursor:pointer; }
.available:hover { outline:2px solid #009fdf; }
.selected { background:#009fdf !important; }
.booked { background:#c0392b; cursor:not-allowed; }
.past { background:#2c2c2c; cursor:not-allowed; }

#info {
  margin-bottom:12px;
  padding:10px 14px;
  border-radius:10px;
  background:rgba(255,255,255,0.08);
  color:#e5e7eb;
}
</style>

<div id="info">Hover over a slot to see details.</div>
<div class="grid" id="grid"></div>

<script>
const data = %s;
const grid = document.getElementById("grid");
const info = document.getElementById("info");

// Header
grid.appendChild(document.createElement("div"));
data.desks.forEach(d => {
  const h = document.createElement("div");
  h.className = "header";
  h.innerText = data.deskNames[d];
  grid.appendChild(h);
});

// Rows
data.times.forEach(t => {
  const tl = document.createElement("div");
  tl.className = "time";
  tl.innerText = t;
  grid.appendChild(tl);

  data.desks.forEach(d => {
    const key = d + "_" + t;
    const c = document.createElement("div");

    if (data.booked.includes(key)) c.className = "cell booked";
    else if (data.past.includes(key)) c.className = "cell past";
    else c.className = "cell available";

    c.onmouseenter = () => {
      info.innerText =
        `${data.dateLabel} · ${data.deskNames[d]} · ${t}`;
    };

    grid.appendChild(c);
  });
});
</script>
""" % (len(DESK_IDS), json.dumps(payload))

st.components.v1.html(html, height=1200)
