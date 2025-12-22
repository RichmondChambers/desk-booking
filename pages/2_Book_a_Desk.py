import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn, init_db
from utils.audit import audit_log
import json

# =====================================================
# PAGE TITLE
# =====================================================
st.title("Book a Desk")

# =====================================================
# SESSION SAFETY
# =====================================================
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", "unknown@richmondchambers.com")
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)
st.session_state.setdefault("selected_cells", [])   # stores JS selections

if st.session_state.user_id is None:
    st.error("User session not initialised. Please start at the home page.")
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
    st.error("Cannot book in the past.")
    st.stop()

if selected_date.weekday() >= 5:
    st.error("Cannot book on weekends.")
    st.stop()

date_iso = selected_date.strftime("%Y-%m-%d")


# =====================================================
# TIME SLOTS — 09:00 to 18:00
# =====================================================
START = time(9, 0)
END = time(18, 0)
SLOT_MINUTES = 30
DESKS = list(range(1, 16))

def generate_slots():
    slots = []
    now = datetime.combine(date.today(), START)
    end = datetime.combine(date.today(), END)
    while now < end:
        slots.append(now.time())
        now += timedelta(minutes=SLOT_MINUTES)
    return slots

SLOTS = generate_slots()

def is_past(slot):
    if selected_date != date.today():
        return False
    return datetime.combine(date.today(), slot) < datetime.now()


# =====================================================
# LOAD EXISTING BOOKINGS
# =====================================================
conn = get_conn()
c = conn.cursor()

rows = c.execute(
    """
    SELECT b.desk_id, b.start_time, b.end_time, u.name, u.id
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE b.date = ?
      AND b.status = 'booked'
    """,
    (date_iso,),
).fetchall()

conn.close()

booked = {}
own_slots = set()

for desk, start, end, user_name, user_id in rows:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    for slot in SLOTS:
        if s <= slot < e:
            booked[(desk, slot)] = f"{user_name} ({start}–{end})"
            if user_id == st.session_state.user_id:
                own_slots.add((desk, slot))


# =====================================================
# CSS
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
.available {
    background: rgba(31,41,55,0.55);
}
.available:hover {
    background: rgba(55,65,81,0.65);
    border-color: rgba(255,255,255,0.25);
}

/* Already booked */
.booked {
    background: rgba(20,83,45,0.55);
    border-color: rgba(34,197,94,0.25);
    cursor: not-allowed;
}

/* User's own booking */
.own {
    background: rgba(30,58,74,0.75);
    border-color: rgba(59,130,246,0.35);
    cursor: not-allowed;
}

/* Past slots */
.past {
    background: rgba(31,41,55,0.25);
    border-color: rgba(255,255,255,0.05);
    cursor: not-allowed;
}

/* Selected by user */
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
# BUILD HTML GRID WITH CLICK + DRAG HANDLING
# =====================================================

# Pass existing booking + selection state to JS
js_payload = {
    "desks": DESKS,
    "times": [slot.strftime("%H:%M") for slot in SLOTS],
    "selected": st.session_state.selected_cells,
    "booked": [f"{d}_{slot.strftime('%H:%M')}" for (d, slot) in booked.keys()],
    "mine": [f"{d}_{slot.strftime('%H:%M')}" for (d, slot) in own_slots],
    "past": [f"{d}_{slot.strftime('%H:%M')}" for (d, slot) in [(d,s) for d in DESKS for s in SLOTS if is_past(s)]],
}

st.components.v1.html(
    f"""
<!DOCTYPE html>
<html>
<head></head>
<body>

<div class="grid" id="grid">

  <!-- TIME + CELLS -->
  {''.join(
      f"""
      <div class='time'>{slot.strftime("%H:%M")}</div>
      {''.join(
          f"<div class='cell' data-key='{desk}_{slot.strftime('%H:%M')}' title='' ></div>"
          for desk in {DESKS}
      )}
      """
      for slot in {json.dumps([slot.strftime("%H:%M") for slot in SLOTS])}
  )}

</div>

<script>
const booked = new Set({json.dumps(js_payload["booked"])});
const mine = new Set({json.dumps(js_payload["mine"])});
const past = new Set({json.dumps(js_payload["past"])});
const selected = new Set({json.dumps(js_payload["selected"])});

let isDragging = false;

// Initial paint
document.querySelectorAll(".cell").forEach(cell => {{
    const key = cell.dataset.key;

    if (booked.has(key)) cell.classList.add("booked");
    else if (mine.has(key)) cell.classList.add("own");
    else if (past.has(key)) cell.classList.add("past");
    else if (selected.has(key)) cell.classList.add("selected");
    else cell.classList.add("available");
}});

function toggleSelect(cell) {{
    const key = cell.dataset.key;
    if (cell.classList.contains("available") || cell.classList.contains("selected")) {{
        if (selected.has(key)) {{
            selected.delete(key);
            cell.classList.remove("selected");
        }} else {{
            selected.add(key);
            cell.classList.add("selected");
        }}

        // Send the updated selection to Streamlit
        window.parent.postMessage({{
            "type": "cell_select",
            "selected": Array.from(selected)
        }}, "*");
    }}
}}

document.querySelectorAll(".cell").forEach(cell => {{
    if (
        cell.classList.contains("booked") ||
        cell.classList.contains("own") ||
        cell.classList.contains("past")
    ) return;

    cell.addEventListener("mousedown", (e) => {{
        isDragging = true;
        toggleSelect(cell);
        e.preventDefault();
    }});

    cell.addEventListener("mouseover", () => {{
        if (isDragging) toggleSelect(cell);
    }});
}});

document.addEventListener("mouseup", () => {{
    isDragging = false;
}});

</script>

</body>
</html>
""",
    height=700,
)


# =====================================================
# RECEIVE MESSAGES FROM JS
# =====================================================
message = st.experimental_get_query_params().get("streamlit_message")

if st.session_state.get("_last_selection_update") != st.session_state.get("selected_cells"):
    pass


# Streamlit receives messages via on_event, processed automatically
def handle_js_event():
    data = st.session_state.get("js_event")
    if data:
        st.session_state.selected_cells = data.get("selected", [])


st.experimental_on_event("cell_select", handle_js_event)


# =====================================================
# SHOW CONFIRMATION BUTTON
# =====================================================
if st.session_state.selected_cells:
    st.success(f"Selected {len(st.session_state.selected_cells)} slot(s)")

    if st.button("Confirm Booking"):
        conn = get_conn()
        c = conn.cursor()

        for key in st.session_state.selected_cells:
            desk, t = key.split("_")
            slot_time = t
            start = slot_time
            end_dt = (
                datetime.combine(date.today(), time.fromisoformat(slot_time))
                + timedelta(minutes=30)
            )
            end = end_dt.strftime("%H:%M")

            c.execute(
                """
                INSERT INTO bookings (user_id, desk_id, date, start_time, end_time, status)
                VALUES (?, ?, ?, ?, ?, 'booked')
                """,
                (st.session_state.user_id, int(desk), date_iso, start, end),
            )

        conn.commit()
        conn.close()

        audit_log(
            st.session_state.user_email,
            "BOOK_DESK",
            f"{len(st.session_state.selected_cells)} slots on {date_iso}"
        )

        st.success("Booking confirmed.")
        st.session_state.selected_cells = []
        st.rerun()
