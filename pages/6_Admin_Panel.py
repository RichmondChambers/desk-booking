import streamlit as st
import pandas as pd

from utils.db import ensure_db, get_conn, write_desks_backup
from utils.auth import require_admin
from utils.audit import log_action
from utils.firestore_client import bulk_cancel_by_desk, list_all_bookings, migrate_sqlite_bookings
from utils.styles import apply_lato_font

st.set_page_config(page_title="Admin Panel", layout="wide")
apply_lato_font()

# ---------------------------------------------------
# PERMISSION CHECK
# ---------------------------------------------------
require_admin()
ensure_db()

st.title("Admin Panel")

# ---------------------------------------------------
# DB HELPERS
# ---------------------------------------------------
def run_db(query: str, params=()):
    conn = get_conn()
    conn.execute(query, params)
    conn.commit()
    conn.close()


def table_exists(table_name: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    conn.close()
    return row is not None


# ---------------------------------------------------
# LOAD USERS
# ---------------------------------------------------
conn = get_conn()
users = conn.execute(
    """
    SELECT id, name, email, role, can_book, is_active
    FROM users
    ORDER BY email
    """
).fetchall()
conn.close()

# ---------------------------------------------------
# USER MANAGEMENT
# ---------------------------------------------------
st.subheader("User Management")

current_user_email = st.session_state.user_email

for user_id, name, email, role, can_book, is_active in users:
    is_self = email == current_user_email

    with st.container(border=True):
        col1, col2, col3, col4, col5, col6 = st.columns([3, 4, 2, 2, 2, 3])

        col1.markdown(f"**{name}**")
        col2.markdown(email)
        col3.markdown(f"Role: **{role}**")
        col4.markdown(f"Can book: **{'Yes' if can_book else 'No'}**")
        col5.markdown(f"Active: **{'Yes' if is_active else 'No'}**")

        with col6:
            # ROLE TOGGLE
            if role == "admin":
                if st.button(
                    "Remove admin",
                    key=f"remove_admin_{user_id}",
                    disabled=is_self,
                ):
                    if not is_self:
                        log_action("REMOVE_ADMIN", f"Removed admin role from {email}")
                        run_db("UPDATE users SET role='user' WHERE id=?", (user_id,))
                        st.rerun()
            else:
                if st.button(
                    "Make admin",
                    key=f"make_admin_{user_id}",
                    disabled=is_self,
                ):
                    log_action("PROMOTE_TO_ADMIN", f"Promoted {email} to admin")
                    run_db("UPDATE users SET role='admin' WHERE id=?", (user_id,))
                    st.rerun()

            # BOOKING PERMISSION
            toggle_label = "Disable booking" if can_book else "Enable booking"
            if st.button(
                toggle_label,
                key=f"toggle_booking_{user_id}",
                disabled=is_self or not is_active,
            ):
                if not is_self:
                    log_action(
                        "TOGGLE_CAN_BOOK",
                        f"{'Disabled' if can_book else 'Enabled'} booking for {email}",
                    )
                    run_db(
                        "UPDATE users SET can_book=? WHERE id=?",
                        (0 if can_book else 1, user_id),
                    )
                    st.rerun()

            # ACTIVE STATUS
            status_label = "Deactivate user" if is_active else "Activate user"
            if st.button(
                status_label,
                key=f"toggle_active_{user_id}",
                disabled=is_self,
            ):
                if not is_self:
                    log_action(
                        "TOGGLE_ACTIVE",
                        f"{'Deactivated' if is_active else 'Activated'} user {email}",
                    )
                    if is_active:
                        run_db(
                            "UPDATE users SET is_active=0, can_book=0 WHERE id=?",
                            (user_id,),
                        )
                    else:
                        run_db(
                            "UPDATE users SET is_active=1 WHERE id=?",
                            (user_id,),
                        )
                    st.rerun()

# ===================================================
# DESK MANAGEMENT
# ===================================================
st.divider()
st.subheader("Desk Management")

conn = get_conn()
desks = conn.execute(
    """
    SELECT id, name, location, is_active, admin_only
    FROM desks
    ORDER BY name
    """
).fetchall()
conn.close()

# ---- CREATE DESK ----
with st.expander("Add new desk"):
    desk_name = st.text_input("Desk name")
    desk_location = st.text_input("Location (optional)")
    desk_admin_only = st.checkbox("Admin-only desk")

    if st.button("Create desk"):
        if not desk_name.strip():
            st.error("Desk name is required.")
        else:
            log_action("CREATE_DESK", f"Created desk '{desk_name}'")
            run_db(
                """
                INSERT INTO desks (name, location, admin_only)
                VALUES (?, ?, ?)
                """,
                (desk_name, desk_location, int(desk_admin_only)),
            )
            write_desks_backup()
            st.success("Desk created.")
            st.rerun()

# ---- EXISTING DESKS ----
for desk_id, name, location, is_active, admin_only in desks:
    with st.container(border=True):
        col1, col2, col3, col4, col5 = st.columns([3, 3, 2, 2, 3])

        col1.markdown(f"**{name}**")
        col2.markdown(location or "—")
        col3.markdown(f"Active: **{'Yes' if is_active else 'No'}**")
        col4.markdown(f"Admin only: **{'Yes' if admin_only else 'No'}**")

        with col5:
            # Enable / Disable desk
            if st.button(
                "Disable" if is_active else "Enable",
                key=f"toggle_desk_active_{desk_id}",
            ):
                log_action(
                    "TOGGLE_DESK_ACTIVE",
                    f"{'Disabled' if is_active else 'Enabled'} desk '{name}'",
                )
                run_db(
                    "UPDATE desks SET is_active=? WHERE id=?",
                    (0 if is_active else 1, desk_id),
                )
                write_desks_backup()
                st.rerun()

            # Admin-only toggle
            if st.button(
                "Remove admin-only" if admin_only else "Make admin-only",
                key=f"toggle_desk_admin_{desk_id}",
            ):
                log_action(
                    "TOGGLE_DESK_ADMIN_ONLY",
                    f"{'Unrestricted' if admin_only else 'Restricted'} desk '{name}'",
                )
                run_db(
                    "UPDATE desks SET admin_only=? WHERE id=?",
                    (0 if admin_only else 1, desk_id),
                )
                write_desks_backup()
                st.rerun()

            # ---- DELETE DESK COMPLETELY ----
            confirm = st.checkbox(
                "Confirm delete",
                key=f"confirm_delete_{desk_id}",
            )

            if confirm and st.button(
                "Delete permanently",
                key=f"delete_desk_{desk_id}",
            ):
                log_action(
                    "DELETE_DESK",
                    f"Deleted desk '{name}' and associated bookings",
                )
                cancelled_count = bulk_cancel_by_desk(
                    desk_id,
                    cancelled_by=st.session_state.user_email,
                    reason="Desk removed",
                )

                run_db("DELETE FROM desks WHERE id = ?", (desk_id,))
                write_desks_backup()

                st.success(
                    f"Desk '{name}' deleted. Cancelled {cancelled_count} bookings."
                )
                st.rerun()

# ---------------------------------------------------
# BOOKINGS OVERVIEW
# ---------------------------------------------------
st.divider()
st.subheader("All Bookings")

bookings = list_all_bookings()
if bookings:
    desk_lookup = {desk[0]: desk[1] for desk in desks}
    df_bookings = pd.DataFrame(
        [
            {
                "ID": booking.booking_id,
                "User": booking.user_email,
                "Desk": desk_lookup.get(booking.desk_id, f"Desk {booking.desk_id}"),
                "Date": booking.booking_date,
                "Start": booking.start_time,
                "End": booking.end_time,
                "Status": booking.status,
                "Checked In": booking.checked_in,
            }
            for booking in bookings
        ]
    )
    st.dataframe(df_bookings, use_container_width=True)
else:
    st.info("No bookings in Firestore.")

# ---------------------------------------------------
# MIGRATION
# ---------------------------------------------------
with st.expander("Migrate existing SQLite bookings to Firestore"):
    st.caption(
        "Run once to copy existing bookings from the local SQLite database. "
        "This does not delete local data."
    )
    if st.button("Run migration"):
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT b.id, b.user_id, b.desk_id, b.date, b.start_time, b.end_time,
                   b.status, b.checked_in, u.email, u.name
            FROM bookings b
            JOIN users u ON u.id = b.user_id
            """
        ).fetchall()
        conn.close()

        stats = migrate_sqlite_bookings(rows)
        st.success(
            f"Migrated bookings. Inserted {stats['inserted']}, "
            f"skipped {stats['skipped']} existing records."
        )

# ---------------------------------------------------
# AUDIT LOG
# ---------------------------------------------------
st.divider()
st.subheader("Audit Log")

conn = get_conn()
logs = conn.execute(
    """
    SELECT timestamp, email, action, details
    FROM audit_log
    ORDER BY timestamp DESC
    LIMIT 200
    """
).fetchall()
conn.close()

df_logs = pd.DataFrame(
    logs,
    columns=["Timestamp", "Actor", "Action", "Details"],
)
st.dataframe(df_logs, use_container_width=True)
