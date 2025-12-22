import streamlit as st
from datetime import datetime, date, time, timedelta
import json

st.title("Book a Desk")

# ---------------------------------------------------
# SESSION SAFETY
# ---------------------------------------------------
if st.session_state.get("user_id") is None:
    st.info("Loading user session…")
    st.stop()

# ---------------------------------------------------
# DATE
# ---------------------------------------------------
selected_date = st.date_input(
    "Select date",
    format="DD/MM/YYYY"
)

# ---------------------------------------------------
# TIME SLOTS
# ---------------------------------------------------
START = time(9, 0)
END = time(18, 0)
SLOT_MINUTES = 30

def generate_slots():
    slots = []
    cur = datetime.combine(date.today(), START)
    end = datetime.combine(date.today(), END)
    while cur < end:
        slots.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=SLOT_MINUTES)
    return slots

time_slots = generate_slots()
desks = list(range(1, 16))

# ---------------------------------------------------
# SELECTION STORAGE
# ---------------------------------------------------
st.session_state.setdefault("grid_selection", [])

# ---------------------------------------------------
# HTML GRID
# ---------------------------------------------------
grid_payload = {
    "desks": desks,
    "times": time_slots,
    "selection": st.session_state.grid_selection,
}

st.components.v1.html(
    f"""
<!DOCTYPE html>
<html>
<head>
<style>
.grid {{
  display: grid;
  grid-template-columns: 80px repeat(15, 1fr);
  gap: 8px;
  font-family: sans-serif;
}}

.cell {{
  height: 32px;
  border-radius: 6px;
  background: #1f2937;
  border: 1px solid #374151;
  cursor: pointer;
}}

.cell:hover {{
  background: #2563eb;
}}

.selected {{
  background: #1d4ed8 !important;
}}

.time {{
  color: #9ca3af;
  font-size: 14px;
  display: flex;
  align-items: center;
}}
</style>
</head>
<body>

<div class="grid" id="grid">
  <div></div>
  {''.join(f'<strong>Desk {d}</strong>' for d in desks)}

  {''.join(
    f'''
    <div class="time">{t}</div>
    {''.join(
        f'<div class="cell" data-desk="{d}" data-time="{t}"></div>'
        for d in desks
    )}
    '''
    for t in time_slots
  )}
</div>

<script>
let selected = new Set();

document.querySelectorAll(".cell").forEach(cell => {{
  cell.addEventListener("click", () => {{
    const key = cell.dataset.desk + "_" + cell.dataset.time;
    if (selected.has(key)) {{
      selected.delete(key);
      cell.classList.remove("selected");
    }} else {{
      selected.add(key);
      cell.classList.add("selected");
    }}

    window.parent.postMessage(
      {{
        type: "desk_selection",
        value: Array.from(selected)
      }},
      "*"
    );
  });
}});
</script>

</body>
</html>
""",
    height=600,
)
