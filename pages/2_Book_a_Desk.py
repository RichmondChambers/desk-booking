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

@@ -97,50 +99,237 @@ slots = generate_slots(selected_date)

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

legend_col, filter_col = st.columns([2, 3])
with legend_col:
    st.markdown(
        """
        <div style="display:flex; gap:16px; align-items:center; margin:8px 0 8px 0; flex-wrap:wrap;">
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

with filter_col:
    hide_past = st.checkbox("Hide past times", value=False)
    show_available_only = st.checkbox("Show only desks with availability", value=False)

filtered_slots = [
    t for t in slots if not (hide_past and is_past_slot(selected_date, t, now))
]

grid_rows = []
for t in filtered_slots:
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

if show_available_only and not grid_df.empty:
    available_desks = [
        desk_name
        for desk_name in DESK_NAMES.values()
        if (grid_df[desk_name] == "Available").any()
    ]
    grid_df = grid_df[["Time"] + available_desks]

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
grid_height = header_height + (row_height * len(filtered_slots)) + 6

if not show_full_day:
    grid_height = 420

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
    width=140,
    minWidth=140,
    maxWidth=160,
    cellStyle=time_cell_style,
    tooltipValueGetter=tooltip_value_getter,
    valueFormatter=None,
    headerName="Time",
)
for desk_name in grid_df.columns:
    if desk_name == "Time":
        continue
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
requirements.txt
+2
-0

streamlit
streamlit-aggrid
pandas
qrcode[pil]
google-auth
google-auth-oauthlib
requests
utils/db.py
+2
-0

import json
import os
import sqlite3
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "data.db"
PERSISTENT_DATA_DIR = Path("/data")

os.environ.setdefault("DESK_BOOKING_DB_PATH", str(DEFAULT_DB_PATH))


# ---------------------------------------------------
# DATABASE PATH RESOLUTION
# ---------------------------------------------------
def _secret_db_path() -> str | None:
    if not hasattr(st, "secrets"):
        return None

    db_path = st.secrets.get("db_path")
    if db_path:
        return db_path

    db_config = st.secrets.get("database")
    if isinstance(db_config, dict):
        return db_config.get("path")

    return None


def _resolve_db_path() -> Path:
    env_path = os.getenv("DESK_BOOKING_DB_PATH")
    if env_path:
        return Path(env_path)

    secret_path = _secret_db_path()
