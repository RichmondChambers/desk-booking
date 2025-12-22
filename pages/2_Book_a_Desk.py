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
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)

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

while cur <= end_dt:
    slots.append(cur.time())
    cur += timedelta(minutes=STEP)

def make_initials(name: str) -> str:
    parts = name.split()
    return "".join(p[0].upper() for p in parts[:2])

def is_past(t: time) -> bool:
    return selected_date == date.today() and datetime.combine(selected_date, t) < datetime.now()

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
    init = make_initials(user_name)

    for t in slots:
        if s <= t < e:
            key = f"{desk_id}_{t.strftime('%H:%M')}"
            booked[key] = {"name": user_name, "initials": init}
            if uid == st.session_state.user_id:
                mine.add(key)

# --------------------------------------------------
# INSTRUCTIONS
# --------------------------------------------------
st.markdown("Select one or more available slots, then confirm your booking.")

# --------------------------------------------------
# GRID (VISUAL SELECTION ONLY)
# --------------------------------------------------
payload = {
    "desks": DESK_IDS,
    "deskNames": DESK_NAMES,
    "times": [t.strftime("%H:%M") for t in slots],
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

.cell {
  height:42px;
  border-radius:10px;
  border:1px solid rgba(255,255,255,0.25);
  display:flex;
  align-items:center;
  justify-content:center;
}

.available { background:#ffffff; cursor:pointer; }
.available:hover { outline:2px solid #009fdf; }
.selected { background:#009fdf !important; }
.own { background:#009fdf; cursor:not-allowed; }
.booked { background:#c0392b; cursor:not-allowed; }
.past { background:#2c2c2c; cursor:not-allowed; }

.cell-label {
  font-size:13px;
  font-weight:600;
  color:#ffffff;
}

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
// font sync
(function sync() {
  try {
    const f = window.parent.getComputedStyle(window.parent.document.body).fontFamily;
    document.body.style.fontFamily = f;
  } catch(e){}
})();

const data = %s;
const grid = document.getElementById("grid");
const info = document.getElementById("info");

let selected = new Set();
let dragging = false;

function status(key) {
  if (data.mine.includes(key)) return "Booked · You";
  if (data.booked[key]) return "Booked · " + data.booked[key].name;
  if (data.past.includes(key)) return "Past";
  return "Available (pending)";
}

// header
grid.appendChild(document.createElement("div"));
data.desks.forEach(d => {
  const h = document.createElement("div");
  h.className = "header";
  h.innerText = data.deskNames[d];
  grid.appendChild(h);
});

// rows
data.times.forEach(t => {
  const tl = document.createElement("div");
  tl.className = "time";
  tl.innerText = t;
  grid.appendChild(tl);

  data.desks.forEach(d => {
    const key = d + "_" + t;
    const c = document.createElement("div");

    if (data.mine.includes(key)) c.className = "cell own";
    else if (data.booked[key]) c.className = "cell booked";
    else if (data.past.includes(key)) c.className = "cell past";
    else c.className = "cell available";

    if (data.booked[key]) {
      const l = document.createElement("div");
      l.className = "cell-label";
      l.innerText = data.booked[key].initials;
      c.appendChild(l);
    }

    c.onmouseenter = () => {
      info.innerText =
        `${data.dateLabel} · ${data.deskNames[d]} · ${t} · ${status(key)}`;
    };

    c.onmousedown = () => {
      if (!c.classList.contains("available")) return;
      dragging = true;
      toggle(c);
    };

    c.onmouseover = () => dragging && toggle(c);
    c.onmouseup = () => dragging = false;

    function toggle(cell) {
      if (cell.classList.contains("selected")) {
        cell.classList.remove("selected");
        selected.delete(key);
      } else {
        cell.classList.add("selected");
        selected.add(key);
      }
    }

    grid.appendChild(c);
  });
});

document.onmouseup = () => dragging = false;
</script>
""" % (len(DESK_IDS), json.dumps(payload))

st.components.v1.html(html, height=1200)

# --------------------------------------------------
# CONFIRM BOOKING
# --------------------------------------------------
st.markdown("### Confirm booking")

if st.button("Confirm booking"):
    # NOTE: pending selection is visual only
    st.warning(
        "Please confirm: booking will apply to the slots you selected visually."
    )
    # At this point, booking logic can be wired once we decide
    # how you want to translate pending selection into bookings
