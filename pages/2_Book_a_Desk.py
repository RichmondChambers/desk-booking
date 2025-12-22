import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
from utils.audit import audit_log
from utils.dates import uk_date
from utils.holidays import is_weekend, is_public_holiday


# ===================================================
# PAGE SETUP
# ===================================================
st.title("Book a Desk")


# ===================================================
# SESSION STATE
# ===================================================
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", "")
st.session_state.setdefault("user_name", "")
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)

st.session_state.setdefault("selected_desk", None)
st.session_state.setdefault("selection_start", None)
st.session_state.setdefault("selection_end", None)

if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

if st.session_state.user_id is None:
    st.error("User session not initialised.")
    st.stop()

is_admin = st.session_state.role == "admin"


# ===================================================
# DATABASE
# ===================================================
conn = get_conn()
c = conn.cursor()


# ===================================================
# DATE SELECTION
# ===================================================
date_choice = st.date_input("Select date")
st.caption(f"Selected date: {uk_date(date_choice)}")

if date_choice < date.today():
    st.error("Bookings cannot be made for past dates.")
    st.stop()

if is_weekend(date_choice):
    st.error("Bookings cannot be made on weekends.")
    st.stop()

if is_public_holiday(date_choice):
    st.error("Bookings cannot be made on UK public holidays.")
    st.stop()

date_iso = date_choice.strftime("%Y-%m-%d")


# ===================================================
# TIME GRID CONFIG (09:00–18:00 EXACT)
# ===================================================
START_HOUR = 9
END_HOUR = 18
SLOT_MINUTES = 30
DESKS = range(1, 16)

def generate_slots():
    slots = []
    current = datetime.combine(date.today(), time(START_HOUR, 0))
    end_of_day = datetime.combine(date.today(), time(END_HOUR, 0))

    while current < end_of_day:
        nxt = current + timedelta(minutes=SLOT_MINUTES)
        if nxt <= end_of_day:
            slots.append((current.time(), nxt.time()))
        current = nxt

    return slots

SLOTS = generate_slots()


# ===================================================
# FETCH EXISTING BOOKINGS
# ===================================================
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

booked = {}
own = set()

for desk, start, end, name, uid in rows:
    start_t = time.fromisoformat(start)
    end_t = time.fromisoformat(end)

    for s, e in SLOTS:
        if s >= start_t and e <= end_t:
            booked[(desk, s)] = f"{name} ({start}–{end})"
            if uid == st.session_state.user_id:
                own.add((desk, s))


# ===================================================
# HELPERS
# ===================================================
def is_past_slot(slot_time: time) -> bool:
    if date_choice != date.today():
        return False
    return datetime.combine(date.today(), slot_time) < datetime.now()

def in_selected_range(desk, slot):
    if (
        st.session_state.selected_desk != desk
        or not st.session_state.selection_start
        or not st.session_state.selection_end
    ):
        return False

    start = min(st.session_state.selection_start, st.session_state.selection_end)
    end = max(st.session_state.selection_start, st.session_state.selection_end)
    return start <= slot <= end


# ===================================================
# CSS STYLES
# ===================================================
st.markdown(
    """
    <style>
    .cell {
        height: 34px;
        border-radius: 6px;
        border: 1px solid #444;
        cursor: pointer;
    }
    .available { background-color: #1e3a2f; }
    .booked { background-color: #4a1f1f; cursor: not-allowed; }
    .own { background-color: #1f3a4a; }
    .selected { background-color: #2563eb; }
    .past { background-color: #2a2a2a; cursor: not-allowed; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ===================================================
# GRID UI
# ===================================================
st.subheader("Select desk and time range")

header = st.columns([1] + [1] * len(DESKS))
header[0].markdown("**Time**")
for i, d in enumerate(DESKS):
    header[i + 1].markdown(f"**Desk {d}**")

for slot_start, slot_end in SLOTS:
    row = st.columns([1] + [1] * len(DESKS))
    row[0].markdown(slot_start.strftime("%H:%M"))

    for i, desk in enumerate(DESKS):
        key = (desk, slot_start)
        booked_info = booked.get(key)
        is_own = key in own
        selected = in_selected_range(desk, slot_start)
        past = is_past_slot(slot_start)

        disabled = (
            past
            or ((booked_info is not None) and not is_admin and not is_own)
        )

        if selected:
            css = "cell selected"
        elif is_own:
            css = "cell own"
        elif booked_info:
            css = "cell booked"
        elif past:
            css = "cell past"
        else:
            css = "cell available"

        if row[i + 1].button(
            " ",
            key=f"{desk}_{slot_start}",
            help=booked_info or "Available",
            disabled=disabled,
        ):
            if st.session_state.selected_desk not in (None, desk):
                st.warning("You can only select one desk.")
            else:
                st.session_state.selected_desk = desk
                if not st.session_state.selection_start:
                    st.session_state.selection_start = slot_start
                    st.session_state.selection_end = slot_start
                else:
                    st.session_state.selection_end = slot_start

        row[i + 1].markdown(
            f"<div class='{css}'></div>",
            unsafe_allow_html=True,
        )


# ===================================================
# CONFIRM BOOKING
# ===================================================
if st.session_state.selection_start and st.session_state.selection_end:
    start_slot = min(
        st.session_state.selection_start,
        st.session_state.selection_end,
    )
    end_slot = (
        datetime.combine(date.today(), max(
            st.session_state.selection_start,
            st.session_state.selection_end,
        )) + timedelta(minutes=SLOT_MINUTES)
    ).time()

    st.success(
        f"Desk {st.session_state.selected_desk} "
        f"from {start_slot.strftime('%H:%M')} "
        f"to {end_slot.strftime('%H:%M')}"
    )

    if st.button("Confirm Booking"):
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
                start_slot.strftime("%H:%M"),
                end_slot.strftime("%H:%M"),
            ),
        )
        conn.commit()

        audit_log(
            st.session_state.user_email,
            "NEW_BOOKING",
            f"desk={st.session_state.selected_desk} "
            f"{start_slot.strftime('%H:%M')}-"
            f"{end_slot.strftime('%H:%M')} "
            f"on {uk_date(date_choice)}",
        )

        st.success("Booking confirmed.")
        st.session_state.selection_start = None
        st.session_state.selection_end = None
        st.session_state.selected_desk = None
        st.rerun()


# ===================================================
# CLEANUP
# ===================================================
conn.close()
