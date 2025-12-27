from pathlib import Path

import streamlit.components.v1 as components


def _resolve_component_root() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    root_component = repo_root / "desk_booking_component"
    if root_component.exists():
        return root_component

    pages_component = (
        Path(__file__).resolve().parent.parent / "pages" / "desk_booking_component"
    )
    if pages_component.exists():
        return pages_component

    raise FileNotFoundError(
        "desk_booking_component directory not found in repo root or pages/"
    )


_DESK_COMPONENT_ROOT = _resolve_component_root()

desk_booking_component = components.declare_component(
    "desk_booking_component",
    path=str(_DESK_COMPONENT_ROOT),
)
