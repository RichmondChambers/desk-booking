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
# DESKS (Desk 1 / Desk 2 / Desk 3)
# =====================================================
DESKS = [1, 2, 3]

# =====================================================
# TIME SLOTS (09:00–18:00, 30 min)
# =====================================================
START = time(9, 0)
END = time(18, 0)
STEP = 30

def generate_slots():
    slots = []
    cur = datetime.combine(date.today(), START)
    end = datetime.combine(date.today(), END)
    while cur < end:
        slots.append(cur.time())
        cur += timedelta(minutes=STEP)
    return slots

SLOTS = generate_slots()

def is_past(t):
    return selected_date == date.today() and datetime.combine(date.today(), t) < datetime.now()

# =====================================================
# LOAD EXISTING BOOKINGS
# =====================================================
conn = get_conn()
rows = conn.execute(
    """
    SELECT b.desk_id, b.start_time, b.end_time, u.name, u.id
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE date = ? AND status='booked'
    """,
    (date_iso,),
).fetchall()
conn.close()

booked = {}
mine = set()

for desk_id, start, end, user_name, uid in rows:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    for slot in SLOTS:
        if s <= slot < e:
            key = f"{desk_id}_{slot.strftime('%H:%M')}"
            booked[key] = f"{user_name} ({start}–{end})"
            if uid == st.session_state.user_id:
                mine.add(key)

# =====================================================
# LEGEND
# =====================================================
st.markdown("""
**Legend**  
⬜ Available 🟦 Your booking 🟥 Booked ⬛ Past
""")

# =====================================================
# JS PAYLOAD
# =====================================================
payload = {
    "desks": DESKS,
    "times": [t.strftime("%H:%M") for t in SLOTS],
    "selected": st.session_state.selected_cells,
    "booked": booked,
    "mine": list(mine),
    "past": [
        f"{d}_{t.strftime('%H:%M')}"
        for d in DESKS
        for t in SLOTS
        if is_past(t)
    ],
}

payload_json = json.dumps(payload)

# =====================================================
# HTML GRID (HEADINGS + DRAG + SCROLL)
# =====================================================
result = st.components.v1.html(
f"""
<!DOCTYPE html>
<html>
<head>
<style>
html, body {{
    margin: 0;
    padding: 0;
    font-family: sans-serif;
    color: #e5e7eb;
}}

.container {{
    max-height: 900px;
    overflow-y: auto;
}}

.grid {{
    display: grid;
    grid-template-columns: 90px repeat(3, 1fr);
    gap: 10px;
    align-items: center;
}}

.header {{
    font-weight: 600;
    text-align: center;
    position: sticky;
    top: 0;
    background: #020617;
    padding: 6px 0;
    z-index: 5;
}}

.time {{
    font-weight: 600;
    text-align: right;
    padding-right: 10px;
}}

.cell {{
    height: 36px;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
    cursor: pointer;
    position: relative;
}}

.available {{ background: #ffffff; }}
.available:hover {{ background: #f3f4f6; }}

.selected,
.own {{ background: #009fdf; }}

.booked {{ background: #b91c1c; cursor: not-allowed; }}
.past {{ background: #1f2937; cursor: not-allowed; }}

.cell[data-tooltip]:hover::after {{
    content: attr(data-tooltip);
    position: absolute;
    bottom: 120%;
    left: 50%;
    transform: translateX(-50%);
    background: #111827;
    color: white;
    padding: 6px 8px;
    font-size: 12px;
    border-radius: 6px;
    white-space: nowrap;
    z-index: 10;
}}
</style>
</head>

<body>

<div class="container">
  <div class="grid" id="grid"></div>
</div>

<script>
const data = {payload_json};
const grid = document.getElementById("grid");
let selected = new Set(data.selected);
let dragging = false;

document.addEventListener("mousedown", () => dragging = true);
document.addEventListener("mouseup", () => dragging = false);

// Header row
grid.appendChild(document.createElement("div"));
["Desk 1","Desk 2","Desk 3"].forEach(h => {{
  const d = document.createElement("div");
  d.className = "header";
  d.innerText = h;
  grid.appendChild(d);
}});

// Time rows
data.times.forEach(time => {{
  const t = document.createElement("div");
  t.className = "time";
  t.innerText = time;
  grid.appendChild(t);

  data.desks.forEach(desk => {{
    const key = desk + "_" + time;
    const cell = document.createElement("div");
    cell.classList.add("cell");

    if (data.booked[key]) {{
      cell.classList.add("booked");
      cell.dataset.tooltip = data.booked[key];
    }}
    else if (data.mine.includes(key)) cell.classList.add("own");
    else if (data.past.includes(key)) cell.classList.add("past");
    else cell.classList.add("available");

    if (selected.has(key)) cell.classList.add("selected");

    if (cell.classList.contains("available") || cell.classList.contains("selected")) {{
      cell.addEventListener("mousedown", () => toggle(key, cell));
      cell.addEventListener("mouseover", () => dragging && toggle(key, cell));
    }}

    grid.appendChild(cell);
  }});
}});

function toggle(key, cell) {{
  if (selected.has(key)) {{
    selected.delete(key);
    cell.classList.remove("selected");
  }} else {{
    selected.add(key);
    cell.classList.add("selected");
  }}
  window.parent.postMessage({{selected:[...selected]}}, "*");
}}
</script>

</body>
</html>
""",
height=950,
)

# =====================================================
# RECEIVE SELECTION
# =====================================================
if isinstance(result, dict) and "selected" in result:
    st.session_state.selected_cells = result["selected"]

# =====================================================
# BOOKING SUMMARY + GROUPING
# =====================================================
if st.session_state.selected_cells:
    grouped = {}

    for k in st.session_state.selected_cells:
        d, t = k.split("_")
        grouped.setdefault(int(d), []).append(time.fromisoformat(t))

    st.subheader("Booking Summary")

    for desk, times in grouped.items():
        times.sort()
        start = times[0]
        end = (datetime.combine(date.today(), times[-1]) + timedelta(minutes=30)).time()
        st.markdown(f"**Desk {desk}** — {start.strftime('%H:%M')}–{end.strftime('%H:%M')}")

    if st.button("Confirm Booking"):
        conn = get_conn()
        c = conn.cursor()

        for desk, times in grouped.items():
            times.sort()
            start = times[0].strftime("%H:%M")
            end = (datetime.combine(date.today(), times[-1]) + timedelta(minutes=30)).time().strftime("%H:%M")

            c.execute(
                """
                INSERT INTO bookings (user_id, desk_id, date, start_time, end_time, status)
                VALUES (?, ?, ?, ?, ?, 'booked')
                """,
                (st.session_state.user_id, desk, date_iso, start, end),
            )

        conn.commit()
        conn.close()

        log_action(
            action="NEW_BOOKING",
            details=f"{len(grouped)} desk(s) booked on {date_iso}",
        )

        st.session_state.selected_cells = []
        st.success("Booking confirmed.")
        st.rerun()
