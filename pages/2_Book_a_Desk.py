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
    st.error("User session not initialised. Please reload the app.")
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
# FETCH BOOKINGS FOR SELECTED DAY / TIME
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
    is_available = desk not in booked
    tooltip = "\n".join(booked.get(desk, [])) or "Available"

    with cols[(desk - 1) % 5]:
        if is_available or is_admin:
            if st.button(
                f"Desk {desk}",
                key=f"desk_{desk}",
                help=tooltip,
            ):
                st.session_state.selected_desk = desk
        else:
            st.button(
                f"Desk {desk}",
                key=f"desk_{desk}",
                disabled=True,
                help=tooltip,
            )


if st.session_state.selected_desk:
    st.success(f"Selected desk: {st.session_state.selected_desk}")

if is_admin:
    st.info("Admin override enabled: occupied desks may be booked.")


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
# WEEKLY DESK PLANNER (VISUAL)
# ---------------------------------------------------
st.markdown("---")
st.subheader("Weekly Desk Planner")

week_start = date_choice - timedelta(days=date_choice.weekday())
week_days = [week_start + timedelta(days=i) for i in range(5)]

planner_rows = c.execute(
    """
    SELECT b.desk_id, b.date, b.start_time, b.end_time, u.name
    FROM bookings b
    JOIN users u ON u.id = b.user_id
    WHERE b.date BETWEEN ? AND ?
      AND b.status = 'booked'
    ORDER BY b.desk_id, b.date, b.start_time
    """,
    (
        week_days[0].strftime("%Y-%m-%d"),
        week_days[-1].strftime("%Y-%m-%d"),
    ),
).fetchall()

planner = {}
for desk, d, start, end, name in planner_rows:
    planner.setdefault((desk, d), []).append(
        f"{name} ({start}–{end})"
    )


# Header
header_cols = st.columns([1] + [2] * 5)
header_cols[0].markdown("### Desk")

for i, d in enumerate(week_days):
    header_cols[i + 1].markdown(
        f"### {d.strftime('%a')}<br>{uk_date(d)}",
        unsafe_allow_html=True,
    )


# Rows
for desk in range(1, 16):
    row_cols = st.columns([1] + [2] * 5)
    row_cols[0].markdown(f"**Desk {desk}**")

    for i, d in enumerate(week_days):
        entries = planner.get((desk, d.strftime("%Y-%m-%d")), [])

        if entries:
            tooltip = "\n".join(entries)
            content = "<br>".join(entries)
            row_cols[i + 1].markdown(
                f"""
                <div style="
                    background-color:#fdecea;
                    border-left:4px solid #e5533d;
                    padding:8px;
                    border-radius:6px;
                    font-size:0.85rem;
                " title="{tooltip}">
                    {content}
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            row_cols[i + 1].markdown(
                """
                <div style="
                    background-color:#e8f5e9;
                    border-left:4px solid #4caf50;
                    padding:8px;
                    border-radius:6px;
                    text-align:center;
                    font-size:0.85rem;
                    color:#2e7d32;
                ">
                    Available
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------
# CLEANUP
# ---------------------------------------------------
conn.close()
