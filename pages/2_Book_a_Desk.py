import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
from utils.audit import audit_log


# =====================================================
# PAGE SETUP
# =====================================================
st.title("Book a Desk")


# =====================================================
# SESSION STATE
# =====================================================
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", "")
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)

st.session_state.setdefault("selected_desk", None)
st.session_state.setdefault("selection", [])

if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

if st.session_state.user_id is None:
    st.error("User session not initialised.")
    st.stop()

is_admin = st.session_state.role == "admin"


# =====================================================
# DATE
# =====================================================
date_choice = st.date_input("Select date")
st.caption(f"Selected date: {date_choice.strftime('%d/%m/%Y')}")

if date_choice < date.today():
    st.error("Cannot book past dates.")
    st.stop()

if date_choice.weekday() >= 5:
    st.error("Weekends disabled.")
    st.stop()

date_iso = date_choice.strftime("%Y-%m-%d")


# =====================================================
# TIME GRID
# =====================================================
START_HOUR = 9
END_HOUR = 18
SLOT_MINUTES = 30
DESKS = range(1, 16)

def time_slots():
    t = datetime.combine(date.today(), time(START_HOUR))
    end = datetime.combine(date.today(), time(END_HOUR))
    out = []
    while t < end:
        out.append(t.time())
        t += timedelta(minutes=SLOT_MINUTES)
    return out

SLOTS = time_slots()


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
            booked[(desk, slot)] = name
            if uid == st.session_state.user_id:
                own.add((desk, slot))


# =====================================================
# CLICK HANDLING (QUERY PARAMS)
# =====================================================
params = st.query_params
if "desk" in params and "slot" in params:
    desk = int(params["desk"])
    slot = time.fromisoformat(params["slot"])

    if st.session_state.selected_desk in (None, desk):
        st.session_state.selected_desk = desk
        if slot not in st.session_state.selection:
            st.session_state.selection.append(slot)
            st.session_state.selection.sort()

    st.query_params.clear()
    st.rerun()


# =====================================================
# CSS
# =====================================================
st.markdown("""
<style>
.grid { display: grid; grid-template-columns: 80px repeat(15, 1fr); gap: 6px; }
.cell {
    height: 34px;
    border-radius: 6px;
    border: 1px solid #444;
    text-align: center;
    cursor: pointer;
}
.available { background:#1e3a2f; }
.booked { background:#4a1f1f; cursor:not-allowed; }
.own { background:#1f3a4a; }
.selected { background:#2563eb; }
.past { background:#2a2a2a; cursor:not-allowed; }
.header { font-weight:600; text-align:center; }
.time { padding-top:6px; }
a { text-decoration:none; color:inherit; }
</style>
""", unsafe_allow_html=True)


# =====================================================
# GRID
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
        past = date_choice == date.today() and datetime.combine(date.today(), slot) < now

        if key in booked and key in own:
            cls = "own"
        elif key in booked:
            cls = "booked"
        elif past:
            cls = "past"
        elif desk == st.session_state.selected_desk and slot in st.session_state.selection:
            cls = "selected"
        else:
            cls = "available"

        if cls in ("booked", "past") and not is_admin:
            html += f"<div class='cell {cls}'></div>"
        else:
            html += (
                f"<a href='?desk={desk}&slot={slot}'>"
                f"<div class='cell {cls}'></div>"
                f"</a>"
            )

html += "</div>"
st.markdown(html, unsafe_allow_html=True)


# =====================================================
# CONFIRM
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
