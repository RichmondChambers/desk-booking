from datetime import datetime, timedelta
from utils.db import get_conn

CHECKIN_GRACE_MINUTES = 30

def _parse_hhmm(t: str) -> datetime:
    return datetime.strptime(t, "%H:%M")

def times_overlap(start1: str, end1: str, start2: str, end2: str) -> bool:
    s1, e1 = _parse_hhmm(start1), _parse_hhmm(end1)
    s2, e2 = _parse_hhmm(start2), _parse_hhmm(end2)
    return max(s1, s2) < min(e1, e2)

def desk_available(desk_id: int, booking_date: str, start_time: str, end_time: str) -> bool:
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute(
        """
        SELECT start_time, end_time
        FROM bookings
        WHERE desk_id=? AND date=? AND status='booked'
        """,
        (desk_id, booking_date)
    ).fetchall()
    conn.close()

    for s, e in rows:
        if times_overlap(start_time, end_time, s, e):
            return False
    return True

def enforce_no_shows(now: datetime | None = None) -> int:
    if now is None:
        now = datetime.now()

    cutoff = now - timedelta(minutes=CHECKIN_GRACE_MINUTES)

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        UPDATE bookings
        SET status='no-show'
        WHERE status='booked'
          AND checked_in=0
          AND datetime(date || ' ' || start_time) < ?
        """,
        (cutoff.strftime("%Y-%m-%d %H:%M:%S"),)
    )
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated
