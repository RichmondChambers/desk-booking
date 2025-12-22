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
# GRID
# --------------------------------------------------
payload = {
    "desks": DESK_IDS,
    "deskNames": DESK_NAMES,
    "times": [t.strftime("%H:%M") for t in slots],
    "selected": st.session_state.selected_cells,
    "booked": booked,
    "mine": list(mine),
    "dateLabel": selected_date.strftime("%d/%m/%Y"),
}

html = """
<div id="grid"></div>

<script>
const data = %s;
let selected = new Set(data.selected);

function sendSelection() {
  window.parent.postMessage(
    { type: "streamlit:setComponentValue", value: Array.from(selected) },
    "*"
  );
}

data.times.forEach(time => {
  data.desks.forEach(desk => {
    const key = desk + "_" + time;
    const div = document.createElement("div");
    div.innerText = key;
    div.style.padding = "6px";
    div.style.margin = "2px";
    div.style.border = "1px solid #ccc";
    div.onclick = () => {
      if (selected.has(key)) selected.delete(key);
      else selected.add(key);
      sendSelection();
    };
    document.getElementById("grid").appendChild(div);
  });
});
</script>
""" % json.dumps(payload)

selected_from_component = st.components.v1.html(html, height=300)

if selected_from_component is not None:
    st.session_state.selected_cells = selected_from_component

# --------------------------------------------------
# CONFIRM
# --------------------------------------------------
if st.session_state.selected_cells:
    st.markdown("### Booking Summary")
    st.write(st.session_state.selected_cells)

    if st.button("Confirm booking"):
        conn = get_conn()
        cur = conn.cursor()
        for key in st.session_state.selected_cells:
            desk_id, t = key.split("_")
            end = (
                datetime.combine(selected_date, time.fromisoformat(t))
                + timedelta(minutes=30)
            ).strftime("%H:%M")
            cur.execute(
                """
                INSERT INTO bookings (user_id, desk_id, date, start_time, end_time, status)
                VALUES (?, ?, ?, ?, ?, 'booked')
                """,
                (st.session_state.user_id, int(desk_id), date_iso, t, end),
            )
        conn.commit()
        conn.close()

        st.session_state.selected_cells = []
        st.success("Booking confirmed.")
        st.rerun()
