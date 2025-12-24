import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
import json

st.set_page_config(page_title="Book a Desk", layout="wide")
st.title("Book a Desk")

# --------------------------------------------------
# SESSION SAFETY (TEMPORARY DEFAULT)
# --------------------------------------------------
st.session_state.setdefault("user_id", 1)

# --------------------------------------------------
# HIDDEN INPUT BRIDGE (CRITICAL)
# --------------------------------------------------
selected_cells_str = st.text_input(
    "selected_cells_hidden",
    value="",
    label_visibility="collapsed",
)

if selected_cells_str:
    selected_cells = selected_cells_str.split(",")
else:
    selected_cells = []

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
    ORDER BY id
    """
).fetchall()
conn.close()

if not desks:
    st.error("No desks found in database.")
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
cur = datetime.combine(selected_date, START)
end_dt = datetime.combine(selected_date, END)

while cur <= end_dt:
    slots.append(cur.time())
    cur += timedelta(minutes=STEP)

def is_past(t):
    return (
        selected_date == date.today()
        and datetime.combine(selected_date, t) < datetime.now()
    )

# --------------------------------------------------
# LOAD EXISTING BOOKINGS
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
# GRID HTML (WITH WORKING BRIDGE)
# --------------------------------------------------
html = """
<style>
.grid { display:grid; grid-template-columns:90px repeat(%d,1fr); gap:12px; }
.time,.header { text-align:center; font-size:14px; }
.header { font-weight:600; }
.cell { height:42px; border-radius:10px; border:1px solid #ccc; }
.available { background:#ffffff; cursor:pointer; }
.selected { background:#009fdf; }
.booked { background:#c0392b; cursor:not-allowed; }
.past { background:#2c2c2c; cursor:not-allowed; }
</style>

<div class="grid" id="grid"></div>

<script>
const data = %s;
const grid = document.getElementById("grid");
let selected = new Set();
let dragging = false;

function pushSelection() {
  const input = window.parent.document.querySelector(
    'input[aria-label="selected_cells_hidden"]'
  );
  if (!input) return;
  input.value = Array.from(selected).join(",");
  input.dispatchEvent(new Event("input", { bubbles: true }));
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

st.components.v1.html(html, height=1100)

# --------------------------------------------------
# CONFIRM BOOKING
# --------------------------------------------------
st.divider()
st.subheader("Confirm booking")

if st.button("Confirm booking", type="primary"):
    if not selected_cells:
        st.warning("Please select a desk and time slot in the grid first.")
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
            (desk_id, date_iso, end.isoformat(), start.isoformat()),
        ).fetchone()

        if conflict:
            conn.close()
            st.error(f"Desk {desk_id} is already booked for that time.")
            st.stop()

        conn.execute(
            """
            INSERT INTO bookings
            (user_id, desk_id, date, start_time, end_time, status, checked_in)
            VALUES (?, ?, ?, ?, ?, 'booked', 0)
            """,
            (
                st.session_state.user_id,
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
