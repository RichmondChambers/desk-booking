import streamlit as st
from datetime import date, timedelta
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
# DATE & TIME INPUTS
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

start_time = st.time_input("Start time")
end_time = st.time_input("End time")

if start_time >= end_time:
    st.warning("End time must be after start time.")
    st.stop()

date_iso = date_choice.strftime("%Y-%m-%d")
start_str = start_time.strftime("%H:%M")
end_str = end_time.strftime("%H:%M")


# ---------------------------------------------------
# FETCH BOOKINGS FOR DAY (WITH USER NAMES)
# ---------------------------------------------------
rows = c.execute(
    """
    SELECT b.desk_id, b.start_time, b.end_time, u.name
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE b.date = ?
      AND b.status = 'booked'
      AND (
          (? BETWEEN b.start_time AND b.end_time)
          OR
          (? BETWEEN b.start_time AND b.end_time)
      )
    """,
    (date_iso, start_str, end_str),
).fetchall()

booked = {}
for desk_id, start, end, name in rows:
    booked.setdefault(desk_id, []).append(
        f"{name} ({start}–{end})"
    )


# ---------------------------------------------------
# CLICKABLE DESK GRID
# ---------------------------------------------------
st.subheader("Desk Availability (click to select)")

cols = st.columns(5)

for desk in range(1, 16):
    tooltip = ""
    available = desk not in booked

    if not available:
        tooltip = "\n".join(booked[desk])

    with cols[(desk - 1) % 5]:
        label = f"Desk {desk}"

        if available or is_admin:
            if st.button(
                label,
                key=f"desk_{desk}",
                help=tooltip or "Available",
            ):
                st.session_state.selected_desk = desk
        else:
            st.button(
                label,
                key=f"desk_{desk}",
                disabled=True,
                help=tooltip,
            )


# ---------------------------------------------------
# SELECTED DESK CONFIRMATION
# ---------------------------------------------------
if st.session_state.selected_desk:
    st.success(f"Selected desk: {st.session_state.selected_desk}")


# ---------------------------------------------------
# ADMIN OVERRIDE NOTICE
# ---------------------------------------------------
if is_admin:
    st.info("Admin override enabled: you may book an occupied desk.")


# ---------------------------------------------------
# CONFIRM BOOKING
# ---------------------------------------------------
if st.button("Confirm Booking"):
    if not st.session_state.selected_desk:
        st.error("Please select a desk.")
    else:
        c.execute(
            """
            INSERT INTO bookings
                (user_id, desk_id, date, start_time, end_time, status)
            VALUES
                (?, ?, ?, ?, ?, 'booked')
            """,
            (
                st.session_state.user_id,
                st.session_state.selected_desk,
                date_iso,
                start_str,
                end_str,
            ),
        )
        conn.commit()

        audit_log(
            st.session_state.user_email,
            "NEW_BOOKING",
            f"desk={st.session_state.selected_desk} "
            f"{start_str}-{end_str} on {uk_date(date_choice)}",
        )

        st.success("Booking confirmed.")
        st.session_state.selected_desk = None
        st.rerun()


# ---------------------------------------------------
# WEEKLY DESK PLANNER
# ---------------------------------------------------
st.markdown("---")
st.subheader("Weekly Desk Planner")

week_start = date_choice - timedelta(days=date_choice.weekday())
days = [week_start + timedelta(days=i) for i in range(5)]

planner = c.execute(
    """
    SELECT b.desk_id, b.date, b.start_time, b.end_time, u.name
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE b.date BETWEEN ? AND ?
      AND b.status = 'booked'
    ORDER BY b.desk_id, b.date
    """,
    (days[0].strftime("%Y-%m-%d"), days[-1].strftime("%Y-%m-%d")),
).fetchall()

planner_map = {}
for desk, d, start, end, name in planner:
    planner_map.setdefault((desk, d), []).append(
        f"{name} ({start}–{end})"
    )

header = ["Desk"] + [uk_date(d) for d in days]
st.markdown(" | ".join(header))
st.markdown(" | ".join(["---"] * len(header)))

for desk in range(1, 16):
    row = [f"Desk {desk}"]
    for d in days:
        cell = planner_map.get((desk, d.strftime("%Y-%m-%d")), [])
        row.append("<br>".join(cell) if cell else "—")
    st.markdown(" | ".join(row), unsafe_allow_html=True)


# ---------------------------------------------------
# CLEANUP
# ---------------------------------------------------
conn.close()
