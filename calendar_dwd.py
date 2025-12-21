import json
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TIMEZONE = "Europe/London"

def _service_account_info() -> dict:
    # Prefer Streamlit Cloud secrets, fall back to local file
    if "service_account" in st.secrets and "json" in st.secrets["service_account"]:
        return json.loads(st.secrets["service_account"]["json"])
    with open("service_account.json", "r", encoding="utf-8") as f:
        return json.load(f)

def calendar_service_for_user(user_email: str):
    info = _service_account_info()
    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=SCOPES,
        subject=user_email,
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

def create_event(*, user_email: str, date: str, start_time: str, end_time: str, desk_name: str) -> str:
    service = calendar_service_for_user(user_email)

    event = {
        "summary": f"Desk Booking – {desk_name}",
        "location": "Office",
        "description": "Desk booking via internal system",
        "start": {"dateTime": f"{date}T{start_time}:00", "timeZone": TIMEZONE},
        "end": {"dateTime": f"{date}T{end_time}:00", "timeZone": TIMEZONE},
    }

    created = service.events().insert(
        calendarId="primary",
        body=event,
    ).execute()

    return created["id"]

def delete_event(*, user_email: str, event_id: str) -> None:
    if not event_id:
        return
    service = calendar_service_for_user(user_email)
    service.events().delete(
        calendarId="primary",
        eventId=event_id,
    ).execute()
