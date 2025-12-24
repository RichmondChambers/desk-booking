# --------------------------------------------------
# CONFIRM BOOKING
# --------------------------------------------------
st.divider()
st.subheader("Confirm booking")

if st.button("Confirm booking", type="primary"):
    if not selected_cells:
        st.error("No desk/time selected.")
        st.stop()

    # Group selected cells by desk
    by_desk = {}
    for cell in selected_cells:
        desk_id, t = cell.split("_")
        by_desk.setdefault(int(desk_id), []).append(
            time.fromisoformat(t)
        )

    conn = get_conn()

    for desk_id, times in by_desk.items():
        times.sort()
        start = times[0]
        end = (
            datetime.combine(selected_date, times[-1])
            + timedelta(minutes=STEP)
        ).time()

        # Conflict check (safety)
        conflict = conn.execute(
            """
            SELECT 1
            FROM bookings
            WHERE desk_id = ?
              AND date = ?
              AND status = 'booked'
              AND start_time < ?
              AND end_time > ?
            """,
            (
                desk_id,
                date_iso,
                end.isoformat(),
                start.isoformat(),
            ),
        ).fetchone()

        if conflict:
            conn.close()
            st.error(f"Desk {desk_id} is already booked for that time.")
            st.stop()

        # Insert booking
        conn.execute(
            """
            INSERT INTO bookings
            (user_id, desk_id, date, start_time, end_time, status, checked_in)
            VALUES (?, ?, ?, ?, ?, 'booked', 0)
            """,
            (
                st.session_state.user_id,
                desk_id,
                date_iso,
                start.isoformat(),
                end.isoformat(),
            ),
        )

    conn.commit()
    conn.close()

    st.success("Booking confirmed.")
    st.rerun()
