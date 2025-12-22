import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
from utils.audit import audit_log
import json

# =====================================================
# PAGE TITLE
# =====================================================
st.title("Book a Desk")

# =====================================================
# SESSION SAFETY (NO AUTH CHECK HERE)
# =====================================================
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", "internal@richmondchambers.com")
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)
st.session_state.setdefault("selected_cells", [])  # JS → Streamlit selections

if st.session_state.user_id is None:
    st.error("User session not initialised.")
    st.stop()

if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

is_admin = st.session_state.role == "admin"

# =====================================================
# DATE PICKER — UK FORMAT
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
# TIME SLOTS 09:00–18:00 (30 min)
# =====================================================
START = time(9, 0)
END = time(18, 0)
STEP = 30
DESKS = list(range(1, 15 + 1))

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
    """Disable past times only for today."""
    if selected_date != date.today():
        return False
    return datetime.combine(date.today(), t) < datetime.now()

# =====================================================
# LOAD EXISTING BOOKINGS
# =====================================================
conn = get_conn()
c = conn.cursor()

rows = c.execute("""
    SELECT b.desk_id, b.start_time, b.end_time, u.name, u.id
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE date = ? AND status='booked'
""", (date_iso,)).fetchall()

conn.close()

booked = {}     # {(desk, time): tooltip}
mine = set()    # user’s own bookings

for desk_id, start, end, user_name, uid in rows:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    for slot in SLOTS:
        if s <= slot < e:
            booked[(desk_id, slot)] = f"{user_name} ({start}–{end})"
            if uid == st.session_state.user_id:
                mine.add((desk_id, slot))

# =====================================================
# CSS STYLING
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
    cursor: pointer;
}

/* Available */
.available { background: rgba(31,41,55,0.55); }
.available:hover {
    background: rgba(55,65,81,0.65);
    border-color: rgba(255,255,255,0.25);
}

/* Booked */
.booked {
    background: rgba(20,83,45,0.55);
    border-color: rgba(34,197,94,0.25);
    cursor: not-allowed;
}

/* Your own booking */
.own {
    background: rgba(30,58,74,0.75);
    border-color: rgba(59,130,246,0.35);
    cursor: not-allowed;
}

/* Past slot */
.past {
    background: rgba(31,41,55,0.25);
    border-color: rgba(255,255,255,0.05);
    cursor: not-allowed;
}

/* Selected for booking */
.selected {
    background: rgba(37,99,235,0.85);
    border-color: rgba(147,197,253,0.8);
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# HEADER ROW
# =====================================================
header_html = "<div class='header-row'><div></div>"
for d in DESKS:
    header_html += f"<div class='header-cell'>Desk {d}</div>"
header_html += "</div>"
st.markdown(header_html, unsafe_allow_html=True)

# =====================================================
# PREPARE PAYLOAD FOR JS
# =====================================================
payload = {
    "desks": DESKS,
    "times": [t.strftime("%H:%M") for t in SLOTS],
    "selected": st.session_state.selected_cells,
    "booked": [f"{d}_{t.strftime('%H:%M')}" for (d, t) in booked.keys()],
    "mine": [f"{d}_{t.strftime('%H:%M')}" for (d, t) in mine],
    "past": [f"{d}_{t.strftime('%H:%M')}" for d in DESKS for t in SLOTS if is_past(t)],
}

payload_json = json.dumps(payload)

# =====================================================
# HTML + JS GRID (SAFE — NO SYNTAX ERRORS)
# =====================================================

html = f"""
<!DOCTYPE html>
<html>
<body>

<div class="grid" id="grid"></div>

<script>
const data = {payload_json};
const grid = document.getElementById("grid");

let selected = new Set(data.selected);
let isDragging = false;

// Build grid
data.times.forEach((time) => {{
    const timeDiv = document.createElement("div");
    timeDiv.className = "time";
    timeDiv.innerText = time;
    grid.appendChild(timeDiv);

    data.desks.forEach((desk) => {{
        const key = desk + "_" + time;
        const cell = document.createElement("div");
        cell.classList.add("cell");

        if (data.booked.includes(key)) cell.classList.add("booked");
        else if (data.mine.includes(key)) cell.classList.add("own");
        else if (data.past.includes(key)) cell.classList.add("past");
        else cell.classList.add("available");

        if (selected.has(key)) cell.classList.add("selected");

        cell.dataset.key = key;

        // Enable clicking only on available or selected
        if (cell.classList.contains("available") || cell.classList.contains("selected")) {{
            cell.addEventListener("mousedown", () => toggle(key, cell));
            cell.addEventListener("mouseover", () => {{ if (isDragging) toggle(key, cell); }});
        }}

        grid.appendChild(cell);
    }});
}});

document.addEventListener("mousedown", () => isDragging = true);
document.addEventListener("mouseup", () => isDragging = false);

function toggle(key, cell) {{
    if (selected.has(key)) {{
        selected.delete(key);
        cell.classList.remove("selected");
    }} else {{
        selected.add(key);
        cell.classList.add("selected");
    }}

    // Send updated selection back to Streamlit
    window.parent.postMessage({{
        type: "cell_select",
        selected: Array.from(selected)
    }}, "*");
}
</script>

</body>
</html>
"""

st.components.v1.html(html, height=700)

# =====================================================
# RECEIVE SELECTIONS FROM JS
# =====================================================
def _handle_message(msg):
    if msg and "selected" in msg:
        st.session_state.selected_cells = msg["selected"]

st.experimental_on_event("cell_select", _handle_message)

# =====================================================
# CONFIRM BOOKING
# =====================================================
if st.session_state.selected_cells:
    st.success(f"{len(st.session_state.selected_cells)} slot(s) selected.")

    if st.button("Confirm Booking"):
        conn = get_conn()
        c = conn.cursor()

        for key in st.session_state.selected_cells:
            desk, t = key.split("_")
            start = t
            end_dt = datetime.combine(date.today(), time.fromisoformat(t)) + timedelta(minutes=30)
            end = end_dt.strftime("%H:%M")

            c.execute("""
                INSERT INTO bookings (user_id, desk_id, date, start_time, end_time, status)
                VALUES (?, ?, ?, ?, ?, 'booked')
            """, (st.session_state.user_id, int(desk), date_iso, start, end))

        conn.commit()
        conn.close()

        audit_log(
            st.session_state.user_email,
            "NEW_BOOKING",
            f"{len(st.session_state.selected_cells)} slots booked on {date_iso}"
        )

        st.session_state.selected_cells = []
        st.success("Booking confirmed.")
        st.rerun()
