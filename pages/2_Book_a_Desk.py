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

# --------------------------------------------------
# DATE PICKER
# --------------------------------------------------
selected_date = st.date_input("Select date", format="DD/MM/YYYY")

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
role = st.session_state.get("role", "user")

conn = get_conn()
desks = conn.execute(
    """
    SELECT id, name
    FROM desks
    WHERE is_active = 1
      AND (admin_only = 0 OR ? = 'admin')
    ORDER BY id
    """,
    (role,),
).fetchall()
conn.close()

if not desks:
    st.error("No desks available.")
    st.stop()

DESK_IDS = [d[0] for d in desks]
DESK_NAMES = {d[0]: d[1] for d in desks}

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
    if selected_date != date.today():
        return False
    return datetime.combine(selected_date, t) < datetime.now()


# --------------------------------------------------
# LOAD BOOKINGS
# --------------------------------------------------
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

booked = {}  # key -> user name
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
# LEGEND
# --------------------------------------------------
st.markdown(
    """
<style>
.legend { display:flex; gap:24px; margin-bottom:16px; font-size:14px; align-items:center; }
.legend-item{ display:flex; gap:10px; align-items:center; }
.legend-sq{ width:18px; height:18px; border-radius:2px; border:1px solid rgba(255,255,255,0.25); }
.legend-available{ background:#ffffff; }
.legend-own{ background:#009fdf; }
.legend-booked{ background:#c0392b; }
.legend-past{ background:#2c2c2c; }
</style>

<div class="legend">
  <div class="legend-item"><span class="legend-sq legend-available"></span> Available</div>
  <div class="legend-item"><span class="legend-sq legend-own"></span> Your booking</div>
  <div class="legend-item"><span class="legend-sq legend-booked"></span> Booked</div>
  <div class="legend-item"><span class="legend-sq legend-past"></span> Past</div>
</div>
""",
    unsafe_allow_html=True,
)

# --------------------------------------------------
# GRID + INTERACTION (STABLE VERSION)
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
    "dateLabel": selected_date.strftime("%d/%m/%Y"),
}

html = """
<style>
html, body { margin:0; padding:0; font-family:inherit; }
* { box-sizing:border-box; font-family:inherit; }

.grid { display:grid; grid-template-columns:90px repeat(%d,1fr); gap:12px; }
.time,.header { color:#e5e7eb; text-align:center; font-size:14px; }
.header { font-weight:600; }
.cell { height:42px; border-radius:10px; border:1px solid rgba(255,255,255,0.25); }
.available { background:#ffffff; cursor:pointer; }
.available:hover { outline:2px solid #009fdf; }
.selected { background:#009fdf !important; }
.own { background:#009fdf; cursor:not-allowed; }
.booked { background:#c0392b; cursor:not-allowed; }
.past { background:#2c2c2c; cursor:not-allowed; }
#info { margin-bottom:12px; padding:10px 14px; border-radius:10px;
        background:rgba(255,255,255,0.08); color:#e5e7eb; min-height:38px; }
</style>

<div id="info">Hover over a slot to see details.</div>
<div class="grid" id="grid"></div>

<script>
// -------- Font sync from Streamlit parent --------
(function syncStreamlitFont() {
  function apply() {
    try {
      const p = window.parent?.document?.body;
      if (!p) return false;
      const f = window.parent.getComputedStyle(p).fontFamily;
      if (f) {
        document.documentElement.style.fontFamily = f;
        document.body.style.fontFamily = f;
        return true;
      }
    } catch(e){}
    return false;
  }
  if (apply()) return;
  let i = 0;
  const t = setInterval(() => {
    if (apply() || ++i > 20) clearInterval(t);
  }, 100);
})();

const data = %s;
const grid = document.getElementById("grid");
const info = document.getElementById("info");

let selected = new Set(data.selected);
let dragging = false;

function statusForCell(key) {
  if (data.mine.includes(key)) return "Your booking";
  if (data.booked[key]) return "Booked";
  if (data.past.includes(key)) return "Past";
  return "Available";
}

function showInfo(deskId, timeStr, key) {
  const deskName = data.deskNames[deskId] ?? String(deskId);
  let text = `${data.dateLabel} · ${deskName} · ${timeStr} · ${statusForCell(key)}`;
  if (data.booked[key]) text += ` · ${data.booked[key]}`;
  info.innerText = text;
}

function toggle(key, el) {
  if (!el.classList.contains("available")) return;
  if (selected.has(key)) {
    selected.delete(key);
    el.classList.remove("selected");
  } else {
    selected.add(key);
    el.classList.add("selected");
  }
}

// Header
grid.appendChild(document.createElement("div"));
data.desks.forEach(d => {
  const h = document.createElement("div");
  h.className = "header";
  h.innerText = data.deskNames[d];
  grid.appendChild(h);
});

// Rows
data.times.forEach(timeStr => {
  const t = document.createElement("div");
  t.className = "time";
  t.innerText = timeStr;
  grid.appendChild(t);

  data.desks.forEach(deskId => {
    const key = deskId + "_" + timeStr;
    const c = document.createElement("div");

    if (data.mine.includes(key)) c.className = "cell own";
    else if (data.booked[key]) c.className = "cell booked";
    else if (data.past.includes(key)) c.className = "cell past";
    else c.className = "cell available";

    if (selected.has(key)) c.classList.add("selected");

    c.onmouseenter = () => showInfo(deskId, timeStr, key);
    c.onmousedown = () => {
      showInfo(deskId, timeStr, key);
      dragging = true;
      toggle(key, c);
    };
    c.onmouseover = () => dragging && toggle(key, c);
    c.onmouseup = () => dragging = false;

    grid.appendChild(c);
  });
});

document.onmouseup = () => dragging = false;
</script>
""" % (len(DESK_IDS), json.dumps(payload))

st.components.v1.html(html, height=1400)
