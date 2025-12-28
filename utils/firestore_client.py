from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Iterable

import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account


BOOKINGS_COLLECTION = "bookings"


class BookingConflict(Exception):
    pass


@dataclass
class BookingRecord:
    booking_id: str
    user_id: int
    user_email: str
    user_name: str
    desk_id: int
    booking_date: str
    start_time: str
    end_time: str
    status: str
    checked_in: bool
    created_at: Any | None
    updated_at: Any | None


@st.cache_resource(show_spinner=False)
def get_firestore_client() -> firestore.Client:
    if "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
        credentials = service_account.Credentials.from_service_account_info(info)
        project_id = info.get("project_id")
        return firestore.Client(project=project_id, credentials=credentials)
    return firestore.Client()


def _format_date(value: date | datetime | str) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _format_time(value: time | str) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)


def _time_to_minutes(value: time | str) -> int:
    if isinstance(value, time):
        return value.hour * 60 + value.minute
    parsed = datetime.strptime(str(value), "%H:%M").time()
    return parsed.hour * 60 + parsed.minute


def _doc_to_record(doc: firestore.DocumentSnapshot) -> BookingRecord:
    data = doc.to_dict() or {}
    return BookingRecord(
        booking_id=doc.id,
        user_id=int(data.get("user_id")) if data.get("user_id") is not None else 0,
        user_email=data.get("user_email", ""),
        user_name=data.get("user_name", ""),
        desk_id=int(data.get("desk_id")) if data.get("desk_id") is not None else 0,
        booking_date=data.get("booking_date", ""),
        start_time=data.get("start_time", ""),
        end_time=data.get("end_time", ""),
        status=data.get("status", ""),
        checked_in=bool(data.get("checked_in", False)),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def _collection() -> firestore.CollectionReference:
    return get_firestore_client().collection(BOOKINGS_COLLECTION)


def is_conflict(desk_id: int, booking_date: date | str, start_time: time | str, end_time: time | str) -> bool:
    booking_date_str = _format_date(booking_date)
    start_minutes = _time_to_minutes(start_time)
    end_minutes = _time_to_minutes(end_time)

    query = (
        _collection()
        .where("desk_id", "==", int(desk_id))
        .where("booking_date", "==", booking_date_str)
        .where("status", "==", "active")
        .where("start_minutes", "<", end_minutes)
    )

    for doc in query.stream():
        data = doc.to_dict() or {}
        if int(data.get("end_minutes", 0)) > start_minutes:
            return True
    return False


def create_booking(
    user_id: int,
    user_email: str,
    user_name: str,
    desk_id: int,
    booking_date: date | str,
    start_time: time | str,
    end_time: time | str,
) -> str:
    booking_date_str = _format_date(booking_date)
    start_time_str = _format_time(start_time)
    end_time_str = _format_time(end_time)
    start_minutes = _time_to_minutes(start_time)
    end_minutes = _time_to_minutes(end_time)

    booking_ref = _collection().document()
    transaction = get_firestore_client().transaction()

    @firestore.transactional
    def _create(transaction: firestore.Transaction) -> None:
        conflict_query = (
            _collection()
            .where("desk_id", "==", int(desk_id))
            .where("booking_date", "==", booking_date_str)
            .where("status", "==", "active")
            .where("start_minutes", "<", end_minutes)
        )
        snapshots = list(transaction.get(conflict_query))
        for doc in snapshots:
            data = doc.to_dict() or {}
            if int(data.get("end_minutes", 0)) > start_minutes:
                raise BookingConflict("Desk already booked for this time window.")

        transaction.set(
            booking_ref,
            {
                "user_id": int(user_id),
                "user_email": user_email,
                "user_name": user_name,
                "desk_id": int(desk_id),
                "booking_date": booking_date_str,
                "start_time": start_time_str,
                "end_time": end_time_str,
                "start_minutes": start_minutes,
                "end_minutes": end_minutes,
                "status": "active",
                "checked_in": False,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        )

    _create(transaction)
    return booking_ref.id


def list_user_bookings(user_id: int, include_cancelled: bool = False) -> list[BookingRecord]:
    query = _collection().where("user_id", "==", int(user_id))
    if not include_cancelled:
        query = query.where("status", "==", "active")
    query = query.order_by("booking_date").order_by("start_minutes")
    return [_doc_to_record(doc) for doc in query.stream()]


def list_all_bookings(filters: dict | None = None) -> list[BookingRecord]:
    query: firestore.Query = _collection()
    if filters:
        if "status" in filters:
            query = query.where("status", "==", filters["status"])
        if "user_id" in filters:
            query = query.where("user_id", "==", int(filters["user_id"]))
        if "desk_id" in filters:
            query = query.where("desk_id", "==", int(filters["desk_id"]))
        if "booking_date" in filters:
            query = query.where("booking_date", "==", _format_date(filters["booking_date"]))
        if "start_date" in filters:
            query = query.where("booking_date", ">=", _format_date(filters["start_date"]))
        if "end_date" in filters:
            query = query.where("booking_date", "<=", _format_date(filters["end_date"]))
    query = query.order_by("booking_date", direction=firestore.Query.DESCENDING).order_by("start_minutes")
    return [_doc_to_record(doc) for doc in query.stream()]


def cancel_booking(booking_id: str, cancelled_by: str, reason: str | None = None) -> None:
    update_payload = {
        "status": "cancelled",
        "cancelled_by": cancelled_by,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if reason:
        update_payload["cancellation_reason"] = reason
    _collection().document(booking_id).update(update_payload)


def bulk_cancel_by_desk(desk_id: int, cancelled_by: str, reason: str | None = None) -> int:
    bookings = list_all_bookings({"desk_id": desk_id, "status": "active"})
    batch = get_firestore_client().batch()
    for booking in bookings:
        ref = _collection().document(booking.booking_id)
        update_payload = {
            "status": "cancelled",
            "cancelled_by": cancelled_by,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        if reason:
            update_payload["cancellation_reason"] = reason
        batch.update(ref, update_payload)
    if bookings:
        batch.commit()
    return len(bookings)


def migrate_sqlite_bookings(rows: Iterable[dict]) -> dict[str, int]:
    client = get_firestore_client()
    batch = client.batch()
    inserted = 0
    skipped = 0

    for row in rows:
        row_data = dict(row)
        booking_id = f"sqlite_{row_data['id']}"
        ref = _collection().document(booking_id)
        if ref.get().exists:
            skipped += 1
            continue
        status = row_data.get("status")
        if status == "booked":
            status = "active"
        batch.set(
            ref,
            {
                "user_id": int(row_data["user_id"]),
                "user_email": row_data.get("email", ""),
                "user_name": row_data.get("name", ""),
                "desk_id": int(row_data["desk_id"]),
                "booking_date": row_data["date"],
                "start_time": row_data["start_time"],
                "end_time": row_data["end_time"],
                "start_minutes": _time_to_minutes(row_data["start_time"]),
                "end_minutes": _time_to_minutes(row_data["end_time"]),
                "status": status,
                "checked_in": bool(row_data.get("checked_in", 0)),
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "migrated_at": firestore.SERVER_TIMESTAMP,
            },
        )
        inserted += 1

    if inserted:
        batch.commit()
    return {"inserted": inserted, "skipped": skipped}
