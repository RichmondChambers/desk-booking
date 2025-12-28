import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta

from utils.db import ensure_db, get_conn
from utils.auth import require_login
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
    while cur < end_dt:
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
    start = prev = available_slots[0]
    for slot in available_slots[1:]:
        if slot == (datetime.combine(selected_date, prev) + timedelta(minutes=STEP)).time():
            prev = slot
        else:
            ranges.append((start, (datetime.combine(selected_date, prev) + timedelta(minutes=STEP)).time()))
            start = prev = slot
    ranges.append((start, (datetime.combine(selected_date, prev) + timedelta(minutes=STEP)).time()))
    return ranges


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
        "SELECT id, name FROM desks WHERE is_active = 1 ORDER BY id"
    ).fetchall()

DESK_IDS = [d["id"] for d in desks]
DESK_NAMES = {d["id"]: d["name"] for d in desks}

# --------------------------------------------------
# TIME SLOTS
# --------------------------------------------------
slots = generate_slots(selected_date)

# --------------------------------------------------
# LOAD BOOKINGS
# --------------------------------------------------
booked = {desk_id: set() for desk_id in DESK_IDS}

with get_conn() as conn:
    rows = conn.execute(
        """
        SELECT desk_id, start_time, end_time
        FROM bookings
        WHERE date = ? AND status = 'booked'
        """,
        (date_iso,),
    ).fetchall()

for r in rows:
    s, e = time.fromisoformat(r["start_time"]), time.fromisoformat(r["end_time"])
    for t in slots:
        if s <= t < e:
            booked[r["desk_id"]].add(t)

# --------------------------------------------------
# GRID DATA
# --------------------------------------------------
grid_rows = []
for t in slots:
    row = {"Time": time_label(t)}
    for d in DESK_IDS:
        if is_past_slot(selected_date, t, now):
            row[DESK_NAMES[d]] = "Past"
        elif t in booked[d]:
            row[DESK_NAMES[d]] = "Booked"
        else:
            row[DESK_NAMES[d]] = "Available"
    grid_rows.append(row)

grid_df = pd.DataFrame(grid_rows)

# --------------------------------------------------
# SELECTION STATE
# --------------------------------------------------
if "grid_selection" not in st.session_state:
    st.session_state.grid_selection = {}

# --------------------------------------------------
# GRID STYLING
# --------------------------------------------------
cell_style = JsCode(
    """
    function(params) {
        const sel = params.context?.selected || {};
        const key = params.colDef.field + "_" + params.data.Time;
        if (sel[key]) {
            return { backgroundColor:"#005f9e", color:"white", fontWeight:"700" };
        }
        if (params.value === "Available") return { backgroundColor:"#009fdf", color:"white" };
        if (params.value === "Booked") return { backgroundColor:"#e0e0e0", color:"#666" };
        if (params.value === "Past") return { backgroundColor:"#f2f2f2", color:"#999" };
        return {};
    }
    """
)

# --------------------------------------------------
# GRID OPTIONS
# --------------------------------------------------
gb = GridOptionsBuilder.from_dataframe(grid_df)
gb.configure_default_column(
    sortable=False,
    filter=False,
    resizable=True,
    cellStyle=cell_style,
    minWidth=160,
)
gb.configure_column("Time", pinned="left", width=120)
gb.configure_grid_options(
    enableRangeSelection=True,
    suppressMultiRangeSelection=False,
    context={"selected": st.session_state.grid_selection},
)

grid_return = AgGrid(
    grid_df,
    gridOptions=gb.build(),
    height=500,
    theme="material",
    allow_unsafe_jscode=True,
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
# PROCESS GRID RANGE SELECTION
# --------------------------------------------------
if isinstance(grid_return, dict) and grid_return.get("colId") not in (None, "Time"):
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
        end_time = (datetime.combine(selected_date, selected_times[-1]) + timedelta(minutes=STEP)).time()

        st.session_state[f"start_{desk_id}_{date_iso}"] = time_label(start_time)
        st.session_state[f"end_{desk_id}_{date_iso}"] = time_label(end_time)

        st.session_state.grid_selection = {
            f"{desk_name}_{time_label(t)}": True for t in selected_times
        }

# --------------------------------------------------
# RANGE SELECTION UI
# --------------------------------------------------
st.subheader("Select time range per desk")

for desk_id in DESK_IDS:
    st.markdown(f"### {DESK_NAMES[desk_id]}")
    available = [t for t in slots if t not in booked[desk_id] and not is_past_slot(selected_date, t, now)]
    if not available:
        st.info("No availability.")
        continue

    labels = [time_label(t) for t in available]
    start = st.selectbox("Start", ["Select"] + labels, key=f"start_{desk_id}_{date_iso}")
    if start != "Select":
        idx = labels.index(start)
        contiguous = labels[idx:]
        end = st.selectbox("End", ["Select"] + contiguous, key=f"end_{desk_id}_{date_iso}")
    st.divider()
