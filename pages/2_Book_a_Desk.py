import streamlit as st
from datetime import datetime, date, time, timedelta
import json

from utils.db import ensure_db, get_conn
from utils.auth import require_login
from utils.styles import apply_lato_font

st.set_page_config(page_title="Book a Desk", layout="wide")
apply_lato_font()
st.title("Book a Desk")

# --------------------------------------------------
# AUTH & PERMISSION CHECK
# --------------------------------------------------
require_login()
ensure_db()

user_id = st.session_state.get("user_id")
can_book = st.session_state.get("can_book", 0)

if not user_id or not can_book:
    st.error("You do not have permission to book desks.")
    st.stop()

# --------------------------------------------------
# HIDDEN INPUT BRIDGE (FOR GRID SELECTION)
# --------------------------------------------------
selected_cells_str = st.text_input(
    "selected_cells_hidden",
    value="",
    key="selected_cells_hidden",
    label_visibility="collapsed",
)

selected_cells = (
    selected_cells_str.split(",") if selected_cells_str else []
)

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
    ORDER BY id
    """
).fetchall()

if not desks:
    conn.close()
    st.error("No desks available.")
    st.stop()

DESK_IDS = [row["id"] for row in desks]
DESK_NAMES = {row["id"]: row["name"] for row in desks}

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
    return (
        selected_date == date.today()
        and datetime.combine(selected_date, t) < datetime.now()
    )

# --------------------------------------------------
# LOAD BOOKINGS
# --------------------------------------------------
rows = conn.execute(
    """
    SELECT desk_id, start_time, end_time
    FROM bookings
    WHERE date = ? AND status = 'booked'
    """,
    (date_iso,),
).fetchall()

booked = set()
for row in rows:
    s = time.fromisoformat(row["start_time"])
    e = time.fromisoformat(row["end_time"])
    for t in slots:
        if s <= t < e:
            booked.add(f"{row['desk_id']}_{t.strftime('%H:%M')}")

conn.close()

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
# GRID HTML + JS (FULL, CORRECT)
# --------------------------------------------------
html = """
<style>
* { box-sizing:border-box; }

.grid {
  display:grid;
  grid-template-columns:90px repeat(%d,1fr);
  gap:12px;
  font-family: "Source Sans Pro", sans-serif;
}
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
  font-family: "Source Sans Pro", sans-serif;
}
</style>

<div id="info">Drag to select contiguous time slots.</div>
<div class="grid" id="grid"></div>

<script>
const data = %s;
const grid = document.getElementById("grid");
const info = document.getElementById("info");

let selected = new Set();
let dragging = false;

function status(key) {
  if (data.booked.includes(key)) return "Booked";
  if (data.past.includes(key)) return "Past";
  return "Available";
}

function pushSelection() {
  const input =
    document.querySelector('input[aria-label="selected_cells_hidden"]') ||
    document.querySelector('textarea[aria-label="selected_cells_hidden"]') ||
    document.querySelector('input[id*="selected_cells_hidden"]') ||
    document.querySelector('textarea[id*="selected_cells_hidden"]') ||
    document.querySelector('input[name*="selected_cells_hidden"]') ||
    document.querySelector('textarea[name*="selected_cells_hidden"]');

  if (!input) return;

  input.value = Array.from(selected).join(",");
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

// Header row
grid.appendChild(document.createElement("div"));
data.desks.forEach(d => {
  const h = document.createElement("div");
  h.className = "header";
  h.innerText = data.deskNames[d];
  grid.appendChild(h);
});

// Time rows
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
      pushSelection();
    }

    grid.appendChild(c);
  });
});

document.onmouseup = () => dragging = false;
</script>
""" % (len(DESK_IDS), json.dumps(payload))

st.html(html, unsafe_allow_javascript=True)

# --------------------------------------------------
# CONFIRM BOOKING
# --------------------------------------------------
st.divider()
st.subheader("Confirm booking")

if st.button("Confirm booking", type="primary"):
    if not selected_cells:
        st.warning("Please select one or more time slots.")
        st.stop()

    by_desk = {}
    for cell in selected_cells:
        desk_id, t = cell.split("_")
        by_desk.setdefault(int(desk_id), []).append(
            time.fromisoformat(t)
        )

    conn = get_conn()

    for desk_id, times in by_desk.items():
        times.sort()

        # Require contiguous slots
        for a, b in zip(times, times[1:]):
            if (
                datetime.combine(selected_date, b)
                - datetime.combine(selected_date, a)
            ) != timedelta(minutes=STEP):
                conn.close()
                st.error("Selected time slots must be continuous.")
                st.stop()

        # Prevent past bookings
        if any(is_past(t) for t in times):
            conn.close()
            st.error("Cannot book time slots in the past.")
            st.stop()

        start = times[0]
        end = (
            datetime.combine(selected_date, times[-1])
            + timedelta(minutes=STEP)
        ).time()

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
            (
                desk_id,
                date_iso,
                end.isoformat(),
                start.isoformat(),
            ),
        ).fetchone()

        if conflict:
            conn.close()
            st.error("One or more selected slots are already booked.")
            st.stop()

        conn.execute(
            """
            INSERT INTO bookings
            (user_id, desk_id, date, start_time, end_time, status, checked_in)
            VALUES (?, ?, ?, ?, ?, 'booked', 0)
            """,
            (
                user_id,
                desk_id,
                date_iso,
                start.isoformat(),
                end.isoformat(),
            ),
        )

    conn.commit()
    conn.close()

    st.success("Booking confirmed.")
    st.rerun()
