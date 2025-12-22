import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
from utils.audit import log_action
import json
import urllib.parse

st.title("Book a Desk")

# --------------------------------------------------
# SESSION SAFETY
# --------------------------------------------------
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)

# Flash message shown in the iframe (persists across reload once)
st.session_state.setdefault("flash_message", "")

if st.session_state.user_id is None:
    st.error("User session not initialised.")
    st.stop()

if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

# --------------------------------------------------
# DATE PICKER (KEYED so it survives URL/query changes)
# --------------------------------------------------
selected_date = st.date_input("Select date", format="DD/MM/YYYY", key="booking_date")

if selected_date < date.today():
    st.error("Cannot book past dates.")
    st.stop()

if selected_date.weekday() >= 5:
    st.error("Desk booking is not available at weekends.")
    st.stop()

date_iso = selected_date.strftime("%Y-%m-%d")

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


def is_past(t: time) -> bool:
    return selected_date == date.today() and datetime.combine(selected_date, t) < datetime.now()


def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return "".join(p[0].upper() for p in parts[:2])


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

if not desks:
    st.warning("No desks available.")
    st.stop()

DESK_IDS = [d[0] for d in desks]
DESK_NAMES = {d[0]: d[1] for d in desks}

# --------------------------------------------------
# LOAD BOOKINGS (for display + conflict checks)
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

booked = {}  # key -> {"name": ..., "initials": ...}
mine = set()

for desk_id, start, end, user_name, uid in rows:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    init = initials(user_name)

    for t in slots:
        if s <= t < e:
            key = f"{desk_id}_{t.strftime('%H:%M')}"
            booked[key] = {"name": user_name, "initials": init}
            if uid == st.session_state.user_id:
                mine.add(key)

# --------------------------------------------------
# QUERY PARAMS (version compatible)
# --------------------------------------------------
def get_query_params():
    # Streamlit >= 1.30
    if hasattr(st, "query_params"):
        return dict(st.query_params)
    # Older Streamlit
    return st.experimental_get_query_params()

def clear_query_params():
    if hasattr(st, "query_params"):
        st.query_params.clear()
    else:
        st.experimental_set_query_params()


params = get_query_params()

# --------------------------------------------------
# HANDLE CONFIRMATION FROM IFRAME (slots=...)
# --------------------------------------------------
if "slots" in params:
    try:
        raw = params["slots"]
        # st.query_params returns string; experimental_get_query_params returns list[str]
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        selected = json.loads(urllib.parse.unquote(raw)) if raw else []
    except Exception:
        selected = []

    # Filter invalid keys & conflicts safely
    valid_selected = []
    conflicts = 0
    invalid = 0

    for key in selected:
        try:
            desk_id_str, t_str = key.split("_", 1)
            desk_id = int(desk_id_str)
            t_obj = time.fromisoformat(t_str)

            if desk_id not in DESK_IDS:
                invalid += 1
                continue
            if t_obj not in slots:
                invalid += 1
                continue
            if is_past(t_obj):
                invalid += 1
                continue
            if key in booked:  # already booked by someone
                conflicts += 1
                continue

            valid_selected.append((desk_id, t_str))
        except Exception:
            invalid += 1
            continue

    if not valid_selected:
        # No slots to book (all invalid/conflicts)
        msg = "No slots were booked."
        if conflicts:
            msg += f" ({conflicts} conflict(s))"
        if invalid:
            msg += f" ({invalid} invalid selection(s))"
        st.session_state.flash_message = msg
        clear_query_params()
        st.rerun()

    # Write bookings
    conn = get_conn()
    try:
        cur = conn.cursor()
        for desk_id, t_str in valid_selected:
            end = (
                datetime.combine(selected_date, time.fromisoformat(t_str))
                + timedelta(minutes=30)
            ).strftime("%H:%M")

            cur.execute(
                """
                INSERT INTO bookings (user_id, desk_id, date, start_time, end_time, status)
                VALUES (?, ?, ?, ?, ?, 'booked')
                """,
                (st.session_state.user_id, desk_id, date_iso, t_str, end),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    log_action(
        action="NEW_BOOKING",
        details=f"{len(valid_selected)} slots on {date_iso}",
    )

    # Persist confirmation message across reload (in iframe)
    st.session_state.flash_message = "Desk booked."

    # Clear params and rerun so the grid reflects DB state (initials)
    clear_query_params()
    st.rerun()

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

st.markdown("Select one or more available slots, then confirm your booking.")

# --------------------------------------------------
# GRID (visual selection + in-iframe confirm button)
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
    "flashMessage": st.session_state.flash_message or "",
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
  letter-spacing:0.5px;
}

#info {
  margin-bottom:12px;
  padding:10px 14px;
  border-radius:10px;
  background:rgba(255,255,255,0.08);
  color:#e5e7eb;
}

.actions {
  margin-top:16px;
  display:flex;
  align-items:center;
  gap:12px;
}

#confirmBtn {
  padding:8px 16px;
  border-radius:8px;
  border:none;
  background:#009fdf;
  color:white;
  font-weight:600;
  cursor:pointer;
}

#confirmBtn:disabled {
  opacity:0.6;
  cursor:not-allowed;
}

#msg {
  color:#22c55e;
  font-weight:600;
}
</style>

<div id="info">Hover over a slot to see details.</div>
<div class="grid" id="grid"></div>

<div class="actions">
  <button id="confirmBtn">Confirm booking</button>
  <span id="msg"></span>
</div>

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
const msg  = document.getElementById("msg");
const confirmBtn = document.getElementById("confirmBtn");

let selected = new Set();
let dragging = false;

if (data.flashMessage) {
  msg.innerText = data.flashMessage;
}

function status(key) {
  if (data.mine.includes(key)) return "Booked · You";
  if (data.booked[key]) return "Booked · " + data.booked[key].name;
  if (data.past.includes(key)) return "Past";
  return "Available";
}

function showInfo(deskId, timeStr, key) {
  const deskName = data.deskNames[deskId] ?? String(deskId);
  info.innerText =
    `${data.dateLabel} · ${deskName} · ${timeStr} · ${status(key)}`;
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

    if (data.booked[key]) {
      const label = document.createElement("div");
      label.className = "cell-label";
      label.innerText = data.booked[key].initials;
      c.appendChild(label);
    }

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

confirmBtn.onclick = () => {
  if (!selected.size) {
    alert("Please select at least one slot.");
    return;
  }
  confirmBtn.disabled = true;
  msg.innerText = "Booking…";

  const q = encodeURIComponent(JSON.stringify(Array.from(selected)));
  // Trigger Streamlit rerun by updating query string.
  window.location.search = "?slots=" + q;
};
</script>
""" % (len(DESK_IDS), json.dumps(payload))

st.components.v1.html(html, height=1400)

# Clear flash message after rendering once so it doesn’t persist forever
if st.session_state.flash_message:
    st.session_state.flash_message = ""
