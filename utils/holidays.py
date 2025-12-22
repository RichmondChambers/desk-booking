from datetime import date

UK_PUBLIC_HOLIDAYS = {
    date(2025, 1, 1),    # New Year's Day
    date(2025, 4, 18),   # Good Friday
    date(2025, 4, 21),   # Easter Monday
    date(2025, 5, 5),    # Early May bank holiday
    date(2025, 5, 26),   # Spring bank holiday
    date(2025, 8, 25),   # Summer bank holiday
    date(2025, 12, 25),  # Christmas Day
    date(2025, 12, 26),  # Boxing Day
}

def is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # Sat/Sun

def is_public_holiday(d: date) -> bool:
    return d in UK_PUBLIC_HOLIDAYS
