from pathlib import Path

import streamlit.components.v1 as components


def get_desk_booking_component():
    component_root = Path(__file__).resolve().parent.parent / "desk_booking_component"
    if not component_root.exists():
        component_root = Path(__file__).resolve().parent / "desk_booking_component"

    return components.declare_component(
        "desk_booking_component",
        path=str(component_root),
    )
