from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from google.cloud import firestore

from utils.firestore_client import get_firestore_client


USERS_COLLECTION = "users"
COUNTERS_COLLECTION = "metadata"
COUNTERS_DOC = "counters"


@dataclass
class UserRecord:
    user_id: int
    name: str
    email: str
    role: str
    can_book: bool
    is_active: bool
    created_at: Any | None
    updated_at: Any | None


def _collection() -> firestore.CollectionReference:
    return get_firestore_client().collection(USERS_COLLECTION)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _doc_to_record(doc: firestore.DocumentSnapshot) -> UserRecord:
    data = doc.to_dict() or {}
    email = data.get("email") or doc.id
    return UserRecord(
        user_id=int(data.get("user_id")) if data.get("user_id") is not None else 0,
        name=data.get("name", ""),
        email=email,
        role=data.get("role", "user"),
        can_book=bool(data.get("can_book", True)),
        is_active=bool(data.get("is_active", True)),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def get_user_by_email(email: str) -> UserRecord | None:
    email_normalized = _normalize_email(email)
    snapshot = _collection().document(email_normalized).get()
    if not snapshot.exists:
        return None
    return _doc_to_record(snapshot)


def list_users() -> list[UserRecord]:
    query = _collection().order_by("email")
    return [_doc_to_record(doc) for doc in query.stream()]


def _next_user_id(transaction: firestore.Transaction) -> int:
    counters_ref = (
        get_firestore_client()
        .collection(COUNTERS_COLLECTION)
        .document(COUNTERS_DOC)
    )
    snapshot = _snapshot_from_transaction(transaction, counters_ref)
    current = 0
    if snapshot.exists:
        current = int(snapshot.to_dict().get("user_id", 0))
    next_id = current + 1
    transaction.set(counters_ref, {"user_id": next_id}, merge=True)
    return next_id


def create_user(
    name: str,
    email: str,
    role: str = "user",
    can_book: bool = True,
    is_active: bool = True,
) -> UserRecord:
    email_normalized = _normalize_email(email)
    user_ref = _collection().document(email_normalized)
    transaction = get_firestore_client().transaction()

    @firestore.transactional
    def _create(transaction: firestore.Transaction) -> UserRecord:
        snapshot = _snapshot_from_transaction(transaction, user_ref)
        if snapshot.exists:
            return _doc_to_record(snapshot)
        user_id = _next_user_id(transaction)
        payload = {
            "user_id": user_id,
            "name": name,
            "email": email_normalized,
            "role": role,
            "can_book": bool(can_book),
            "is_active": bool(is_active),
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        transaction.set(user_ref, payload)
        return UserRecord(
            user_id=user_id,
            name=name,
            email=email_normalized,
            role=role,
            can_book=bool(can_book),
            is_active=bool(is_active),
            created_at=None,
            updated_at=None,
        )

    return _create(transaction)


def update_user(email: str, updates: dict[str, Any]) -> None:
    email_normalized = _normalize_email(email)
    payload = dict(updates)
    payload.pop("email", None)
    payload["updated_at"] = firestore.SERVER_TIMESTAMP
    _collection().document(email_normalized).set(payload, merge=True)


def _snapshot_from_transaction(
    transaction: firestore.Transaction,
    reference: firestore.DocumentReference,
) -> firestore.DocumentSnapshot:
    snapshot = transaction.get(reference)
    if hasattr(snapshot, "exists"):
        return snapshot
    return next(iter(snapshot))


def migrate_sqlite_users(rows: Iterable[dict]) -> dict[str, int]:
    client = get_firestore_client()
    batch = client.batch()
    inserted = 0
    skipped = 0
    max_user_id = 0

    for row in rows:
        row_data = dict(row)
        email = row_data.get("email")
        if not email:
            skipped += 1
            continue
        email_normalized = _normalize_email(email)
        ref = _collection().document(email_normalized)
        if ref.get().exists:
            skipped += 1
            continue
        user_id = int(row_data.get("id") or 0)
        max_user_id = max(max_user_id, user_id)
        batch.set(
            ref,
            {
                "user_id": user_id,
                "name": row_data.get("name", ""),
                "email": email_normalized,
                "role": row_data.get("role", "user"),
                "can_book": bool(row_data.get("can_book", 1)),
                "is_active": bool(row_data.get("is_active", 1)),
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "migrated_at": firestore.SERVER_TIMESTAMP,
            },
        )
        inserted += 1

    if inserted:
        batch.commit()
        counters_ref = client.collection(COUNTERS_COLLECTION).document(COUNTERS_DOC)
        snapshot = counters_ref.get()
        current = 0
        if snapshot.exists:
            current = int(snapshot.to_dict().get("user_id", 0))
        if max_user_id > current:
            counters_ref.set({"user_id": max_user_id}, merge=True)
    return {"inserted": inserted, "skipped": skipped}
