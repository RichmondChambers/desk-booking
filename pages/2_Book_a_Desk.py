import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
from utils.audit import audit_log


# =====================================================
# PAGE SETUP
# =====================================================
st.title("Book a Desk")


# =====================================================
# SESSION STATE (ROBUST LAZY INITIALISATION)
# =====================================================
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", None)
st.session_state.setdefault("user_name", None)
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)

st.session_state.setdefault("selected_desk", None)
st.session_state.setdefault("selection", [])

# ---- Bootstrap user if not already initialised ----
if st.session_state.user_id is None:
    user = st.experimental_user

    if not user or not user.is_authenticated:
        st.error("Please sign in to use the desk booking system.")
        st.stop()

    email = user.email.lower()
    name = user.name or email.split("@")[0]

    conn = get_conn()
    c = conn.cursor()

    row = c.execute(
        "SELECT id, name, role, can_book FROM users WHERE email=?",
        (email,),
    ).fetchone()

    if not row:
        c.execute(
            "INSERT INTO users (name, email, role, can_book) VALUES (?, ?, 'user', 1)",
            (name, email),
        )
        conn.commit()
        row = c.execute(
            "SELECT id, name, role, can_book FROM users WHERE email=?",
            (email,),
        ).fetchone()

    conn.close()

    st.session_state.user_id = row[0]
    st.session_state.user_name = row[1]
    st.session_state.role = row[2]
    st.session_state.can_book = row[3]
    st.session_state.user_email = email

# ---- Permission check ----
if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

is_admin = st.session_state.role == "admin"


# =====================================================
# DATE SELECTION
# =====================================================
date_choice = st.date_input("Select date")
st.caption(f"Selected date: {date_choice.strftime('%d/%m/%Y')}")

if date_choice < date.today():
    st.error("Bookings cannot be made for past dates.")
    st.stop()

if date_choice.weekday() >= 5:
    st.error("Bookings cannot be made on weekends.")
    st.stop()

date_iso = date_choice.strftime("%Y-%m-%d")


# =====================================================
# TIME GRID CONFIG (09:00–18:00)
# =====================================================
START_HOUR = 9
END_HOUR = 18
SLOT_MINUTES = 30
DESKS = list(range(1, 16))

def generate_slots():
    slots = []
    current = datetime.combine(date.today(), time(START_HOUR))
    end = datetime.combine(date.today(), time(END_HOUR))
    while current < end:
        slots.append(current.time())
        current += timedelta(minutes=SLOT_MINUTES)
    return slots

SLOTS = generate_slots()


# =====================================================
# LOAD BOOKINGS
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
own = set()

for desk, start, end, name, uid in rows:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    for slot in SLOTS:
        if s <= slot < e:
            booked[(desk, slot)] = f"{name} ({start}–{end})"
            if uid == st.session_state.user_id:
                own.add((desk, slot))


# =====================================================
# HANDLE CLICK / DRAG EVENTS (QUERY PARAMS)
# =====================================================
params = st.query_params

if "desk" in params and "slot" in params:
    clicked_desk = int(params["desk"])
    clicked_slot = time.fromisoformat(params["slot"])

    if st.session_state.selected_desk in (None, clicked_desk):
        st.session_state.selected_desk = clicked_desk
        if clicked_slot not in st.session_state.selection:
            st.session_state.selection.append(clicked_slot)
            st.session_state.selection.sort()

    st.query_params.clear()
    st.rerun()


# =====================================================
# HELPERS
# =====================================================
def is_past(slot):
    if date_choice != date.today():
        return False
    return datetime.combine(date.today(), slot) < datetime.now()


# =====================================================
# CSS + JS (CLICK + DRAG)
# =====================================================
st.markdown("""
<style>
.grid {
    display: grid;
    grid-template-columns: 80px repeat(15, 1fr);
    gap: 6px;
}

.grid a {
    pointer-events: auto !important;
    display: block;
}

.cell {
    height: 34px;
    border-radius: 6px;
    border: 1px solid #444;
    cursor: pointer;
}

.available { background:#1e3a2f; }
.booked { background:#4a1f1f; cursor:not-allowed; }
.own { background:#1f3a4a; }
.selected { background:#2563eb; }
.past { background:#2a2a2a; cursor:not-allowed; }

.header {
    font-weight:600;
    text-align:center;
}

.time {
    padding-top:6px;
    font-weight:500;
}

a {
    text-decoration:none;
    color:inherit;
}
</style>

<script>
let isDragging = false;

document.addEventListener("mousedown", () => isDragging = true);
document.addEventListener("mouseup", () => isDragging = false);

document.addEventListener("mouseover", (e) => {
    if (!isDragging) return;
    const target = e.target.closest("a");
    if (target) window.location = target.href;
});
</script>
""", unsafe_allow_html=True)


# =====================================================
# GRID RENDER
# =====================================================
st.subheader("Select desk and time range")

html = "<div class='grid'>"
html += "<div></div>"

for d in DESKS:
    html += f"<div class='header'>Desk {d}</div>"

now = datetime.now()

for slot in SLOTS:
    html += f"<div class='time'>{slot.strftime('%H:%M')}</div>"

    for desk in DESKS:
        key = (desk, slot)
        past = is_past(slot)
        tooltip = booked.get(key, "")

        if key in own:
            css = "own"
        elif key in booked:
            css = "booked"
        elif past:
            css = "past"
        elif desk == st.session_state.selected_desk and slot in st.session_state.selection:
            css = "selected"
        else:
            css = "available"

        if (css in ("booked", "past")) and not is_admin:
            html += f"<div class='cell {css}' title='{tooltip}'></div>"
        else:
            html += (
                f"<a href='?desk={desk}&slot={slot}'>"
                f"<div class='cell {css}' title='{tooltip or 'Available'}'></div>"
                f"</a>"
            )

html += "</div>"
st.markdown(html, unsafe_allow_html=True)


# =====================================================
# CONFIRM BOOKING
# =====================================================
if st.session_state.selection:
    start = min(st.session_state.selection)
    end = (
        datetime.combine(date.today(), max(st.session_state.selection))
        + timedelta(minutes=SLOT_MINUTES)
    ).time()

    st.success(
        f"Desk {st.session_state.selected_desk} "
        f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
    )

    if st.button("Confirm Booking"):
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO bookings
            (user_id, desk_id, date, start_time, end_time, status)
            VALUES (?, ?, ?, ?, ?, 'booked')
            """,
            (
                st.session_state.user_id,
                st.session_state.selected_desk,
                date_iso,
                start.strftime("%H:%M"),
                end.strftime("%H:%M"),
            ),
        )
        conn.commit()
        conn.close()

        audit_log(
            st.session_state.user_email,
            "NEW_BOOKING",
            f"desk={st.session_state.selected_desk} "
            f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')} "
            f"on {date_choice.strftime('%d/%m/%Y')}",
        )

        st.success("Booking confirmed.")
        st.session_state.selection.clear()
        st.session_state.selected_desk = None
        st.rerun()
