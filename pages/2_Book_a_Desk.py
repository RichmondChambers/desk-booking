import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn, init_db
import json
import urllib.parse

# --------------------------------------------------
# PAGE SETUP
# --------------------------------------------------
st.set_page_config(page_title="Book a Desk", layout="wide")
st.title("Book a Desk")

# --------------------------------------------------
# ENSURE DATABASE IS INITIALISED
# --------------------------------------------------
# This MUST run before any SELECT/INSERT queries
init_db()

# --------------------------------------------------
# SESSION SAFETY
# --------------------------------------------------
st.session_state.setdefault("user_id", 1)  # temporary safe default

# --------------------------------------------------
# READ GRID SELECTION FROM QUERY PARAMS
# --------------------------------------------------
selected_cells_param = st.query_params.get("selected", "")
selected_cells = selected_cells_param.split(",") if selected_cells_param else []

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
conn.close()

if not desks:
    st.error("No desks found.")
    st.stop()

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
    "selected": selected_cells,
}

# --------------------------------------------------
# GRID HTML
# --------------------------------------------------
html = """
<div class="grid"></div>

<script>
const data = %s;
const grid = document.querySelector(".grid");
let selected = new Set(data.selected);

function updateURL() {
  const params = new URLSearchParams(window.location.search);
  params.set("selected", Array.from(selected).join(","));
  window.history.replaceState({}, "", "?" + params.toString());
}

grid.style.display = "grid";
grid.style.gridTemplateColumns = "90px repeat(" + data.desks.length + ",1fr)";
grid.style.gap = "10px";

// header
grid.appendChild(document.createElement("div"));
data.desks.forEach(d => {
  const h = document.createElement("div");
  h.textContent = data.deskNames[d];
  grid.appendChild(h);
});

// rows
data.times.forEach(t => {
  const tl = document.createElement("div");
  tl.textContent = t;
  grid.appendChild(tl);

  data.desks.forEach(d => {
    const key = d + "_" + t;
    const c = document.createElement("div");
    c.style.height = "36px";
    c.style.border = "1px solid #ccc";

    if (data.booked.includes(key) || data.past.includes(key)) {
      c.style.background = "#aaa";
    } else {
      c.style.cursor = "pointer";
      if (selected.has(key)) c.style.background = "#009fdf";

      c.onclick = () => {
        if (selected.has(key)) selected.delete(key);
        else selected.add(key);
        updateURL();
        location.reload();
      };
    }
    grid.appendChild(c);
  });
});
</script>
""" % json.dumps(payload)

st.components.v1.html(html, height=1000)

# --------------------------------------------------
# CONFIRM BOOKING
# --------------------------------------------------
st.divider()
st.subheader("Confirm booking")

if st.button("Confirm booking", type="primary"):
    if not selected_cells:
        st.warning("Please select a desk and time slot.")
        st.stop()

    by_desk = {}
    for cell in selected_cells:
        desk_id, t = cell.split("_")
        by_desk.setdefault(int(desk_id), []).append(time.fromisoformat(t))

    conn = get_conn()

    for desk_id, times in by_desk.items():
        times.sort()
        start = times[0]
        end = (datetime.combine(selected_date, times[-1]) + timedelta(minutes=STEP)).time()

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
    st.query_params.clear()
    st.rerun()
