from datetime import date

from app.errors import APIError


def parse_date(value, name="date"):
    if value is None:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        raise APIError(f"'{name}' must be YYYY-MM-DD")