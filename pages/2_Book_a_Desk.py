import re
import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta

from utils.db import ensure_db, get_conn
from utils.audit import log_action
from utils.auth import require_login
from utils.firestore_client import BookingConflict, create_booking, list_all_bookings
from st_aggrid import (
    AgGrid,
    DataReturnMode,
    GridOptionsBuilder,
    GridUpdateMode,
    JsCode,
)

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
    slots = []
    cur = datetime.combine(selected_date, START)
    end_dt = datetime.combine(selected_date, END)
    while cur <= end_dt:
        slots.append(cur.time())
        cur += timedelta(minutes=STEP)
    return slots


def is_past_slot(selected_date: date, t: time, now: datetime) -> bool:
    return selected_date == date.today() and datetime.combine(selected_date, t) < now


def time_label(t: time) -> str:
    return t.strftime("%H:%M")


def availability_ranges(available_slots: list[time], selected_date: date):
    if not available_slots:
        return []
    ranges = []
    range_start = previous = available_slots[0]
    for slot in available_slots[1:]:
        expected_next = (
            datetime.combine(selected_date, previous) + timedelta(minutes=STEP)
        ).time()
        if slot == expected_next:
            previous = slot
            continue
        ranges.append(
            (
                range_start,
                (datetime.combine(selected_date, previous) + timedelta(minutes=STEP)).time(),
            )
        )
        range_start = previous = slot
    ranges.append(
        (
            range_start,
            (datetime.combine(selected_date, previous) + timedelta(minutes=STEP)).time(),
        )
    )
    return ranges


def user_initials(name: str | None, email: str | None) -> str:
    raw = (name or "").strip()
    if not raw:
        raw = (email or "").split("@")[0]
    parts = [part for part in re.split(r"[\s._-]+", raw) if part]
    if not parts:
        return ""
    if len(parts) >= 2:
        initials = f"{parts[0][0]}{parts[1][0]}"
    else:
        initials = parts[0][:2]
    return initials.upper()


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
booked = {desk_id: set() for desk_id in DESK_IDS}
booked_initials = {desk_id: {} for desk_id in DESK_IDS}

bookings = list_all_bookings({"booking_date": date_iso, "status": "active"})

for booking in bookings:
    s = time.fromisoformat(booking.start_time)
    e = time.fromisoformat(booking.end_time)
    initials = user_initials(booking.user_name, booking.user_email)
    for t in slots:
        if s <= t < e:
            booked[booking.desk_id].add(t)
            if initials:
                booked_initials[booking.desk_id][t] = initials

# --------------------------------------------------
# AVAILABILITY GRID
# --------------------------------------------------
st.markdown(
    """
    <style>
    .ag-header-cell-label {
        justify-content: center;
    }
    .ag-header-cell-text {
        text-align: center;
        width: 100%;
    }
    .ag-cell {
        text-align: center;
    }
    [data-testid="stCheckbox"] label {
        justify-content: center;
        text-align: center;
        width: 100%;
    }
    </style>
    <h2 style="text-align:center;">Availability overview</h2>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div style="display:flex; gap:16px; align-items:center; justify-content:center; margin:8px 0; text-align:center;">
        <div><span style="display:inline-block;width:14px;height:14px;background:#ffffff;border-radius:3px;border:1px solid #d0d0d0;"></span> Available</div>
        <div><span style="display:inline-block;width:14px;height:14px;background:#009fdf;border-radius:3px;"></span> Booked (initials)</div>
        <div><span style="display:inline-block;width:14px;height:14px;background:#f2f2f2;border-radius:3px;"></span> Past</div>
    </div>
    """,
    unsafe_allow_html=True,
)

filtered_slots = slots

grid_rows = []
for t in filtered_slots:
    row = {"Time": time_label(t)}
    for desk_id in DESK_IDS:
        if is_past_slot(selected_date, t, now):
            row[DESK_NAMES[desk_id]] = "Past"
        elif t in booked[desk_id]:
            initials = booked_initials[desk_id].get(t)
            row[DESK_NAMES[desk_id]] = (
                f"Booked:{initials}" if initials else "Booked"
            )
        else:
            row[DESK_NAMES[desk_id]] = "Available"
    grid_rows.append(row)

grid_df = pd.DataFrame(grid_rows)

# --------------------------------------------------
# GRID SELECTION STATE
# --------------------------------------------------
if "grid_selected_cells" not in st.session_state:
    st.session_state.grid_selected_cells = {}

# --------------------------------------------------
# GRID STYLING (WITH SELECTION HIGHLIGHT)
# --------------------------------------------------
cell_style = JsCode(
    """
    function(params) {
        const sel = params.context.selected || {};
        const key = params.colDef.field + "_" + params.data.Time;
        if (sel[key]) {
            return {backgroundColor:"#005f9e", color:"white", fontWeight:"700", textAlign:"center"};
        }
        if (params.value === "Available") return {backgroundColor:"#ffffff", color:"#111", textAlign:"center"};
        if (String(params.value).startsWith("Booked")) {
            return {backgroundColor:"#009fdf", color:"#ffffff", fontWeight:"700", textAlign:"center"};
        }
        if (params.value === "Past") return {backgroundColor:"#f2f2f2", color:"#999", textAlign:"center"};
        return {textAlign:"center"};
    }
    """
)

value_formatter = JsCode(
    """
    function(params) {
        if (params.value === "Available") return "";
        if (String(params.value).startsWith("Booked:")) {
            return String(params.value).split(":")[1];
        }
        if (params.value === "Booked") return "×";
        if (params.value === "Past") return "–";
        return params.value;
    }
    """
)

row_height = 28
header_height = 52
grid_height = header_height + (row_height * len(filtered_slots)) + 6

grid_builder = GridOptionsBuilder.from_dataframe(grid_df)
grid_builder.configure_default_column(
    resizable=True,
    sortable=False,
    filter=False,
    cellStyle=cell_style,
    valueFormatter=value_formatter,
    minWidth=90,
    width=100,
)
grid_builder.configure_column("Time", pinned="left", width=90)
grid_builder.configure_grid_options(
    headerHeight=header_height,
    rowHeight=row_height,
    enableRangeSelection=True,
    suppressMultiRangeSelection=False,
    context={"selected": st.session_state.grid_selected_cells},
)

grid_return = AgGrid(
    grid_df,
    gridOptions=grid_builder.build(),
    height=grid_height,
    fit_columns_on_grid_load=False,
    allow_unsafe_jscode=True,
    theme="material",
    update_mode=GridUpdateMode.MODEL_CHANGED,
    data_return_mode=DataReturnMode.CUSTOM,
    custom_jscode_for_grid_return=JsCode(
        """
        function({eventData}) {
            const api = eventData.api;
            const ranges = api.getCellRanges();
            if (!ranges || !ranges.length) return {};
            const r = ranges[0];
            return {
                colId: r.columns[0].getColId(),
                startRow: r.startRow.rowIndex,
                endRow: r.endRow.rowIndex
            };
        }
        """
    ),
)

# --------------------------------------------------
# GRID RANGE PREFILL + HIGHLIGHT
# --------------------------------------------------
if grid_return and grid_return.get("colId") not in (None, "Time"):
    desk_name = grid_return["colId"]
    desk_id = next(k for k, v in DESK_NAMES.items() if v == desk_name)

    start_idx = min(grid_return["startRow"], grid_return["endRow"])
    end_idx = max(grid_return["startRow"], grid_return["endRow"])

    selected_times = [
        datetime.strptime(grid_df.iloc[i]["Time"], "%H:%M").time()
        for i in range(start_idx, end_idx + 1)
        if grid_df.iloc[i][desk_name] == "Available"
    ]

    if selected_times:
        start_time = selected_times[0]
        end_time = (
            datetime.combine(selected_date, selected_times[-1]) + timedelta(minutes=STEP)
        ).time()

        st.session_state[f"start_{desk_id}_{date_iso}"] = time_label(start_time)
        st.session_state[f"end_{desk_id}_{date_iso}"] = time_label(end_time)

        st.session_state.grid_selected_cells = {
            f"{desk_name}_{time_label(t)}": True for t in selected_times
        }

# --------------------------------------------------
# RANGE SELECTION UI (UNCHANGED)
# --------------------------------------------------
st.subheader("Select time range per desk")
st.caption("Pick a start time first, then choose an end time from the contiguous availability.")

desk_col, start_col, end_col = st.columns(3)

with desk_col:
    desk_id = st.selectbox(
        "Desk",
        DESK_IDS,
        format_func=lambda desk: DESK_NAMES[desk],
        key=f"desk_{date_iso}",
    )

available = [
    t for t in slots
    if t not in booked[desk_id]
    and not is_past_slot(selected_date, t, now)
]

if not available:
    with start_col:
        st.selectbox(
            "Start time",
            ["No available slots"],
            disabled=True,
            key=f"start_{desk_id}_{date_iso}",
        )
    with end_col:
        st.selectbox(
            "End time",
            ["No available slots"],
            disabled=True,
            key=f"end_{desk_id}_{date_iso}",
        )
    st.info("No available slots.")
else:
    labels = [time_label(t) for t in available]
    with start_col:
        start_value = st.selectbox(
            "Start time",
            ["Select start"] + labels,
            key=f"start_{desk_id}_{date_iso}",
        )

    if start_value != "Select start":
        start_time = datetime.strptime(start_value, "%H:%M").time()
        idx = available.index(start_time)
        contiguous = available[idx:]
        end_options = [
            time_label(
                (datetime.combine(selected_date, t) + timedelta(minutes=STEP)).time()
            )
            for t in contiguous
        ]
    else:
        end_options = []

    with end_col:
        end_value = st.selectbox(
            "End time",
            ["Select end"] + end_options,
            key=f"end_{desk_id}_{date_iso}",
            disabled=not end_options,
        )

can_confirm = start_value != "Select start" and end_value != "Select end"
booking_success = st.session_state.pop("booking_success", False)

confirm_col, message_col = st.columns([1, 3])

with confirm_col:
    confirm_clicked = st.button("Confirm desk booking", disabled=not can_confirm)

with message_col:
    if booking_success:
        st.success("Desk booked")

if confirm_clicked:
    if not can_confirm:
        st.error("Please select a start and end time.")
    else:
        start_time = datetime.strptime(start_value, "%H:%M").time()
        end_time = datetime.strptime(end_value, "%H:%M").time()
        if start_time >= end_time:
            st.error("End time must be after start time.")
        else:
            range_slots = []
            current = datetime.combine(selected_date, start_time)
            end_dt = datetime.combine(selected_date, end_time)
            while current < end_dt:
                range_slots.append(current.time())
                current += timedelta(minutes=STEP)

            if any(slot not in available for slot in range_slots):
                st.error("Selected time range is no longer available.")
            else:
                try:
                    create_booking(
                        user_id=user_id,
                        user_email=st.session_state.user_email,
                        user_name=st.session_state.user_name,
                        desk_id=desk_id,
                        booking_date=date_iso,
                        start_time=start_value,
                        end_time=end_value,
                    )
                except BookingConflict:
                    st.error("Selected time range is no longer available.")
                else:
                    log_action(
                        "BOOKING_CREATED",
                        f"desk_id={desk_id}, date={date_iso}, start={start_value}, end={end_value}",
                    )
                    st.session_state.booking_success = True
                    st.rerun()
