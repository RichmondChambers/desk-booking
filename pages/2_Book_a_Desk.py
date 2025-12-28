import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta

from utils.db import ensure_db, get_conn
from utils.auth import require_login
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
STEP = 30
START = time(9, 0)
END = time(18, 0)


# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def generate_slots(selected_date: date):
    """
    Generate slot start times from START (inclusive) to END (exclusive) in STEP-minute increments.
    Example: 09:00 ... 17:30 for END=18:00 and STEP=30.
    """
    slots = []
    cur = datetime.combine(selected_date, START)
    end_dt = datetime.combine(selected_date, END)

    while cur < end_dt:  # END is exclusive to avoid a useless trailing 18:00 slot
        slots.append(cur.time())
        cur += timedelta(minutes=STEP)

    return slots


def is_past_slot(selected_date: date, t: time, now: datetime) -> bool:
    return selected_date == date.today() and datetime.combine(selected_date, t) < now


def time_label(t: time) -> str:
    return t.strftime("%H:%M")


# --------------------------------------------------
# PAGE SETUP
# --------------------------------------------------
st.set_page_config(page_title="Book a Desk", layout="wide")
st.title("Book a Desk")

# --------------------------------------------------
# AUTH & DB
# --------------------------------------------------
require_login()
ensure_db()

user_id = st.session_state.get("user_id")
can_book = st.session_state.get("can_book", 0)

if not user_id or not can_book:
    st.error("You do not have permission to book desks.")
    st.stop()

# --------------------------------------------------
# DATE PICKER
# --------------------------------------------------
selected_date = st.date_input("Select date", format="DD/MM/YYYY")

if selected_date.weekday() >= 5:
    st.warning("Desk booking is not available at weekends.")
    st.stop()

date_iso = selected_date.strftime("%Y-%m-%d")
now = datetime.now()

# --------------------------------------------------
# LOAD DESKS
# --------------------------------------------------
with get_conn() as conn:
    desks = conn.execute(
        """
        SELECT id, name
        FROM desks
        WHERE is_active = 1
        ORDER BY id
        """
    ).fetchall()

if not desks:
    st.error("No desks available.")
    st.stop()

DESK_IDS = [row["id"] for row in desks]
DESK_NAMES = {row["id"]: row["name"] for row in desks}

# --------------------------------------------------
# TIME SLOTS
# --------------------------------------------------
slots = generate_slots(selected_date)

# --------------------------------------------------
# LOAD EXISTING BOOKINGS
# --------------------------------------------------
# booked[desk_id] = set(time objects that are taken)
booked = {desk_id: set() for desk_id in DESK_IDS}

with get_conn() as conn:
    rows = conn.execute(
        """
        SELECT desk_id, start_time, end_time
        FROM bookings
        WHERE date = ?
          AND status = 'booked'
        """,
        (date_iso,),
    ).fetchall()

for row in rows:
    s = time.fromisoformat(row["start_time"])
    e = time.fromisoformat(row["end_time"])
    for t in slots:
        if s <= t < e:
            booked[row["desk_id"]].add(t)

# --------------------------------------------------
# AVAILABILITY GRID
# --------------------------------------------------
st.subheader("Availability overview")

view_mode = st.radio("View density", ["Compact", "Comfortable"], horizontal=True)
show_full_day = st.checkbox("Show full day without scrolling", value=True)

grid_rows = []
for t in slots:
    row = {"Time": time_label(t)}
    for desk_id in DESK_IDS:
        if is_past_slot(selected_date, t, now):
            status = "Past"
        elif t in booked[desk_id]:
            status = "Booked"
        else:
            status = "Available"
        row[DESK_NAMES[desk_id]] = status
    grid_rows.append(row)

grid_df = pd.DataFrame(grid_rows)

cell_style = JsCode(
    """
    function(params) {
        if (params.value === "Available") {
            return {
                backgroundColor: "#009fdf",
                color: "white",
                fontWeight: "600",
                textAlign: "center"
            };
        }
        if (params.value === "Booked") {
            return {
                backgroundColor: "#e0e0e0",
                color: "#666",
                textAlign: "center"
            };
        }
        if (params.value === "Past") {
            return {
                backgroundColor: "#f2f2f2",
                color: "#999",
                textAlign: "center"
            };
        }
        return {};
    }
    """
)

value_formatter = JsCode(
    """
    function(params) {
        if (params.value === "Available") {
            return "";
        }
        if (params.value === "Booked") {
            return "×";
        }
        if (params.value === "Past") {
            return "–";
        }
        return params.value;
    }
    """
)

time_cell_style = JsCode(
    """
    function(params) {
        return {
            backgroundColor: "#ffffff",
            color: "#222",
            fontWeight: "600",
            textAlign: "center"
        };
    }
    """
)

tooltip_value_getter = JsCode(
    """
    function(params) {
        return params.value;
    }
    """
)

row_height = 28 if view_mode == "Compact" else 36
header_height = 52 if view_mode == "Compact" else 60
grid_height = header_height + (row_height * len(slots)) + 6

if not show_full_day:
    grid_height = 420

st.markdown(
    """
    <div style="display:flex; gap:16px; align-items:center; margin:8px 0 16px 0; flex-wrap:wrap;">
        <div style="display:flex; align-items:center; gap:6px;">
            <span style="display:inline-block; width:14px; height:14px; background:#009fdf; border-radius:3px;"></span>
            <span>Available</span>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
            <span style="display:inline-block; width:14px; height:14px; background:#e0e0e0; border-radius:3px;"></span>
            <span>Booked</span>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
            <span style="display:inline-block; width:14px; height:14px; background:#f2f2f2; border-radius:3px;"></span>
            <span>Past</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

grid_builder = GridOptionsBuilder.from_dataframe(grid_df)
grid_builder.configure_default_column(
    resizable=True,
    sortable=False,
    filter=False,
    cellStyle=cell_style,
    valueFormatter=value_formatter,
    minWidth=160,
    wrapHeaderText=True,
    autoHeaderHeight=True,
    tooltipValueGetter=tooltip_value_getter,
)
grid_builder.configure_column(
    "Time",
    pinned="left",
    width=110,
    minWidth=110,
    maxWidth=130,
    cellStyle=time_cell_style,
    tooltipValueGetter=tooltip_value_getter,
    valueFormatter=None,
    headerName="Time",
)
for desk_id in DESK_IDS:
    desk_name = DESK_NAMES[desk_id]
    grid_builder.configure_column(
        desk_name,
        headerName=desk_name,
        minWidth=160,
        maxWidth=240,
        valueFormatter=value_formatter,
        cellStyle=cell_style,
        tooltipValueGetter=tooltip_value_getter,
    )
grid_builder.configure_grid_options(
    headerHeight=header_height,
    rowHeight=row_height,
    suppressSizeToFit=True,
)
grid_options = grid_builder.build()

AgGrid(
    grid_df,
    gridOptions=grid_options,
    height=grid_height,
    fit_columns_on_grid_load=False,
    allow_unsafe_jscode=True,
    theme="material",
)

# --------------------------------------------------
# RANGE SELECTION UI (per desk)
# --------------------------------------------------
st.subheader("Select time range per desk")

selections = {}  # desk_id -> (start_time, end_time)

for desk_id in DESK_IDS:
    st.markdown(f"### {DESK_NAMES[desk_id]}")

    available = [
        t for t in slots
        if t not in booked[desk_id]
        and not is_past_slot(selected_date, t, now)
    ]

    if not available:
        st.info("No available slots.")
        continue

    labels = [time_label(t) for t in available]

    start_label = st.selectbox(
        "Start time",
        ["—"] + labels,
        key=f"start_{desk_id}_{date_iso}",
    )

    end_label = st.selectbox(
        "End time",
        ["—"] + labels,
        key=f"end_{desk_id}_{date_iso}",
    )

    if start_label != "—" and end_label != "—":
        start = time.fromisoformat(start_label)
        end = time.fromisoformat(end_label)

        if end <= start:
            st.error("End time must be after start time.")
        else:
            # Ensure the entire interval is available (not just endpoints)
            interval_slots = []
            cur_dt = datetime.combine(selected_date, start)
            end_dt = datetime.combine(selected_date, end)
            while cur_dt < end_dt:
                interval_slots.append(cur_dt.time())
                cur_dt += timedelta(minutes=STEP)

            if any(
                (t in booked[desk_id]) or is_past_slot(selected_date, t, now)
                for t in interval_slots
            ):
                st.error("Selected range includes unavailable time slots.")
            else:
                selections[desk_id] = (start, end)

# --------------------------------------------------
# CONFIRM BOOKING
# --------------------------------------------------
st.divider()
st.subheader("Confirm booking")

if st.button("Confirm booking", type="primary", use_container_width=True):

    if not selections:
        st.warning("Please select at least one booking.")
        st.stop()

    # Defensive: reject past selections on submit
    for desk_id, (start, end) in selections.items():
        if is_past_slot(selected_date, start, now):
            st.error("Cannot book time slots in the past.")
            st.stop()

    with get_conn() as conn:
        for desk_id, (start, end) in selections.items():

            # Application-level overlap check (still required for friendly messaging)
            conflict = conn.execute(
                """
                SELECT 1
                FROM bookings
                WHERE desk_id = ?
                  AND date = ?
                  AND status = 'booked'
                  AND start_time < ?
                  AND end_time > ?
                """,
                (desk_id, date_iso, end.isoformat(), start.isoformat()),
            ).fetchone()

            if conflict:
                st.error(f"{DESK_NAMES[desk_id]} has a conflicting booking.")
                st.stop()

            # Insert
            conn.execute(
                """
                INSERT INTO bookings
                (user_id, desk_id, date, start_time, end_time, status, checked_in)
                VALUES (?, ?, ?, ?, ?, 'booked', 0)
                """,
                (user_id, desk_id, date_iso, start.isoformat(), end.isoformat()),
            )

        conn.commit()

    st.success("Booking confirmed.")
    st.rerun()
