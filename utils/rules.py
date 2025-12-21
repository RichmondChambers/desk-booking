from datetime import datetime, timedelta
from utils.db import get_conn
from utils.audit import audit_log

def enforce_no_shows(now):
    """Mark bookings as no-show if they were never checked in."""
    conn = get_conn()
    c = conn.cursor()

    today = now.strftime("%Y-%m-%d")
    now_hhmm = now.strftime("%H:%M")

    no_shows = c.execute("""
        SELECT id, user_id
        FROM bookings
        WHERE date=? AND end_time < ? AND checked_in=0 AND status='booked'
    """, (today, now_hhmm)).fetchall()

    for booking_id, user_id in no_shows:
        c.execute(
            "UPDATE bookings SET status='no_show' WHERE id=?",
            (booking_id,),
        )
        audit_log(
            None,
            "AUTO_NO_SHOW",
            f"booking={booking_id}, user_id={user_id}",
        )

    conn.commit()
    conn.close()
