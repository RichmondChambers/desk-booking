import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.db import get_conn
from utils.audit import audit_log
from utils.dates import uk_date
from utils.holidays import is_weekend, is_public_holiday


# ---------------------------------------------------
# PAGE SETUP
# ---------------------------------------------------
st.title("Book a Desk")


# ---------------------------------------------------
# SESSION STATE SAFETY
# ---------------------------------------------------
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_email", "internal.user@richmondchambers.com")
st.session_state.setdefault("role", "user")
st.session_state.setdefault("can_book", 1)
st.session_state.setdefault("selected_cells", set())
st.session_state.setdefault("selected_desk", None)

if not st.session_state.can_book:
    st.error("You are not permitted to book desks.")
    st.stop()

if st.session_state.user_id is None:
    st.error("User session not initialised.")
    st.stop()

is_admin = st.session_state.role == "admin"


# ---------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------
conn = get_conn()
c = conn.cursor()


# ---------------------------------------------------
# DATE SELECTION
# ---------------------------------------------------
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


# ---------------------------------------------------
# TIME GRID CONFIGURATION
# ---------------------------------------------------
START_HOUR = 8
END_HOUR = 18
SLOT_MINUTES = 30

def generate_time_slots():
    slots = []
    current = time(START_HOUR, 0)
    while current < time(END_HOUR, 0):
        end = (datetime.combine(date.today(), current) +
               timedelta(minutes=SLOT_MINUTES)).time()
        slots.append((current, end))
        current = end
    return slots

time_slots = generate_time_slots()
desks = range(1, 16)


# ---------------------------------------------------
# FETCH EXISTING BOOKINGS
# ---------------------------------------------------
rows = c.execute(
    """
    SELECT b.desk_id, b.start_time, b.end_time, u.name
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE b.date = ?
      AND b.status = 'booked'
    """,
    (date_iso,),
).fetchall()

# Map: {(desk, slot_start): "Name (start–end)"}
booked_cells = {}

for desk_id, start, end, name in rows:
    start_t = time.fromisoformat(start)
    end_t = time.fromisoformat(end)

    for slot_start, slot_end in time_slots:
        if slot_start >= start_t and slot_end <= end_t:
            booked_cells[(desk_id, slot_start)] = f"{name} ({start}–{end})"


# ---------------------------------------------------
# GRID UI
# ---------------------------------------------------
st.subheader("Select desk and time slots")

header_cols = st.columns([1] + [1] * len(desks))
header_cols[0].markdown("**Time**")

for i, desk in enumerate(desks):
    header_cols[i + 1].markdown(f"**Desk {desk}**")

for slot_start, slot_end in time_slots:
    row_cols = st.columns([1] + [1] * len(desks))
    row_cols[0].markdown(f"{slot_start.strftime('%H:%M')}")

    for i, desk in enumerate(desks):
        key = (desk, slot_start)
        booked_info = booked_cells.get(key)

        disabled = booked_info is not None and not is_admin
        selected = key in st.session_state.selected_cells

        label = "■" if selected else " "

        if row_cols[i + 1].button(
            label,
            key=f"{desk}_{slot_start}",
            disabled=disabled,
            help=booked_info or "Available",
        ):
            # Enforce single-desk selection
            if st.session_state.selected_desk not in (None, desk):
                st.warning("You can only book one desk at a time.")
            else:
                st.session_state.selected_desk = desk
                if selected:
                    st.session_state.selected_cells.remove(key)
                else:
                    st.session_state.selected_cells.add(key)


# ---------------------------------------------------
# CONFIRM BOOKING
# ---------------------------------------------------
if st.session_state.selected_cells:
    selected_times = sorted(
        [slot for desk, slot in st.session_state.selected_cells]
    )

    start_time = selected_times[0].strftime("%H:%M")
    end_time = (
        datetime.combine(date.today(), selected_times[-1]) +
        timedelta(minutes=SLOT_MINUTES)
    ).time().strftime("%H:%M")

    st.success(
        f"Booking Desk {st.session_state.selected_desk} "
        f"from {start_time} to {end_time}"
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
                start_time,
                end_time,
            ),
        )
        conn.commit()

        audit_log(
            st.session_state.user_email,
            "NEW_BOOKING",
            f"desk={st.session_state.selected_desk} "
            f"{start_time}-{end_time} on {uk_date(date_choice)}",
        )

        st.success("Booking confirmed.")
        st.session_state.selected_cells.clear()
        st.session_state.selected_desk = None
        st.rerun()


# ---------------------------------------------------
# CLEANUP
# ---------------------------------------------------
conn.close()
