import streamlit as st
import pandas as pd

from utils.db import get_conn
from utils.permissions import require_admin
from utils.audit import log_action

st.set_page_config(page_title="Admin Panel", layout="wide")

# ---------------------------------------------------
# PERMISSION CHECK
# ---------------------------------------------------
require_admin()

st.title("Admin Panel")

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

for user_id, name, email, role, can_book, is_active in users:

    is_self = email == st.session_state.user_email

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
                if st.button("Remove admin", key=f"remove_admin_{user_id}", disabled=is_self):
                    log_action("REMOVE_ADMIN", f"Removed admin role from {email}")
                    conn = get_conn()
                    conn.execute("UPDATE users SET role='user' WHERE id=?", (user_id,))
                    conn.commit()
                    conn.close()
                    st.rerun()
            else:
                if st.button("Make admin", key=f"make_admin_{user_id}", disabled=is_self):
                    log_action("PROMOTE_TO_ADMIN", f"Promoted {email} to admin")
                    conn = get_conn()
                    conn.execute("UPDATE users SET role='admin' WHERE id=?", (user_id,))
                    conn.commit()
                    conn.close()
                    st.rerun()

            # BOOKING PERMISSION
            toggle_label = "Disable booking" if can_book else "Enable booking"
            if st.button(toggle_label, key=f"toggle_booking_{user_id}", disabled=is_self or not is_active):
                log_action(
                    "TOGGLE_CAN_BOOK",
                    f"{'Disabled' if can_book else 'Enabled'} booking for {email}",
                )
                conn = get_conn()
                conn.execute(
                    "UPDATE users SET can_book=? WHERE id=?",
                    (0 if can_book else 1, user_id),
                )
                conn.commit()
                conn.close()
                st.rerun()

            # ACTIVE STATUS
            status_label = "Deactivate user" if is_active else "Activate user"
            if st.button(status_label, key=f"toggle_active_{user_id}", disabled=is_self):
                log_action(
                    "TOGGLE_ACTIVE",
                    f"{'Deactivated' if is_active else 'Activated'} user {email}",
                )
                conn = get_conn()
                if is_active:
                    conn.execute(
                        "UPDATE users SET is_active=0, can_book=0 WHERE id=?",
                        (user_id,),
                    )
                else:
                    conn.execute(
                        "UPDATE users SET is_active=1 WHERE id=?",
                        (user_id,),
                    )
                conn.commit()
                conn.close()
                st.rerun()

# ===================================================
# DESK MANAGEMENT  ⭐ NEW SECTION ⭐
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
            conn = get_conn()
            conn.execute(
                """
                INSERT INTO desks (name, location, admin_only)
                VALUES (?, ?, ?)
                """,
                (desk_name, desk_location, int(desk_admin_only)),
            )
            conn.commit()
            conn.close()
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
            # Toggle active
            if st.button(
                "Disable" if is_active else "Enable",
                key=f"toggle_desk_active_{desk_id}",
            ):
                log_action(
                    "TOGGLE_DESK_ACTIVE",
                    f"{'Disabled' if is_active else 'Enabled'} desk '{name}'",
                )
                conn = get_conn()
                conn.execute(
                    "UPDATE desks SET is_active=? WHERE id=?",
                    (0 if is_active else 1, desk_id),
                )
                conn.commit()
                conn.close()
                st.rerun()

            # Toggle admin-only
            if st.button(
                "Remove admin-only" if admin_only else "Make admin-only",
                key=f"toggle_desk_admin_{desk_id}",
            ):
                log_action(
                    "TOGGLE_DESK_ADMIN_ONLY",
                    f"{'Restricted' if not admin_only else 'Unrestricted'} desk '{name}'",
                )
                conn = get_conn()
                conn.execute(
                    "UPDATE desks SET admin_only=? WHERE id=?",
                    (0 if admin_only else 1, desk_id),
                )
                conn.commit()
                conn.close()
                st.rerun()

# ---------------------------------------------------
# BOOKINGS OVERVIEW
# ---------------------------------------------------
st.divider()
st.subheader("All Bookings")

conn = get_conn()
bookings = conn.execute(
    """
    SELECT id, user_id, desk_id, date, start_time, end_time, status, checked_in
    FROM bookings
    ORDER BY date DESC
    """
).fetchall()
conn.close()

df_bookings = pd.DataFrame(
    bookings,
    columns=["ID", "User ID", "Desk", "Date", "Start", "End", "Status", "Checked In"],
)
st.dataframe(df_bookings, use_container_width=True)

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
