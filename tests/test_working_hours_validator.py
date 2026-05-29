import pytest
from django.core.exceptions import ValidationError

from apps.restaurants.models import validate_working_hours

_VALID = {
    "mon": {"open": "09:00", "close": "22:00"},
    "fri": {"open": "10:00", "close": "23:59"},
}


def test_valid_working_hours() -> None:
    validate_working_hours(_VALID)


def test_rejects_non_dict() -> None:
    with pytest.raises(ValidationError, match="Must be an object"):
        validate_working_hours("09:00-22:00")


def test_rejects_unknown_day() -> None:
    with pytest.raises(ValidationError, match="Unknown day key"):
        validate_working_hours({"monday": {"open": "09:00", "close": "22:00"}})


def test_rejects_missing_close_key() -> None:
    with pytest.raises(ValidationError, match="exactly 'open' and 'close'"):
        validate_working_hours({"mon": {"open": "09:00"}})


def test_rejects_bad_format() -> None:
    with pytest.raises(ValidationError, match="HH:MM format"):
        validate_working_hours({"mon": {"open": "9:00", "close": "22:00"}})


def test_rejects_hours_out_of_range() -> None:
    with pytest.raises(ValidationError, match="out of range"):
        validate_working_hours({"mon": {"open": "99:99", "close": "22:00"}})


def test_rejects_minutes_out_of_range() -> None:
    with pytest.raises(ValidationError, match="out of range"):
        validate_working_hours({"mon": {"open": "09:60", "close": "22:00"}})


def test_allows_overnight_hours() -> None:
    validate_working_hours({"mon": {"open": "22:00", "close": "02:00"}})


def test_rejects_equal_open_close() -> None:
    with pytest.raises(ValidationError, match="cannot be equal"):
        validate_working_hours({"mon": {"open": "09:00", "close": "09:00"}})
