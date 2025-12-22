from datetime import datetime, date

def uk_date(value) -> str:
    """
    Converts a date, datetime, or ISO date string (YYYY-MM-DD)
    to UK format DD/MM/YYYY for display.
    """
    if value is None:
        return ""

    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")

    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return str(value)
