"""Validation with physical limits using the Pydantic schema + domain rules."""
from typing import List

from ..config import get_physical_limits
from ..schemas import SensorReading

VALID_STATUS = {"ONLINE", "OFFLINE"}
VALID_GEN = {"AVAILABLE", "UNAVAILABLE", "RUNNING", "OFF", "ON", None}


class InvalidReadingError(Exception):
    def __init__(self, issues: List[str]):
        self.issues = issues
        super().__init__("; ".join(issues))


def _iso_ok(ts: str) -> bool:
    from datetime import datetime
    try:
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_reading(reading: SensorReading) -> List[str]:
    """Validate a reading against physical limits. Returns list of issues (empty = valid)."""
    issues: List[str] = []
    limits = get_physical_limits()

    if not _iso_ok(reading.timestamp):
        issues.append(f"Invalid timestamp format: {reading.timestamp!r} (use ISO-8601).")

    for field, (lo, hi) in limits.items():
        val = getattr(reading, field, None)
        if val is None:
            continue
        if not (lo <= val <= hi):
            issues.append(
                f"{field} = {val} outside physical range [{lo}, {hi}]."
            )

    if reading.solar_status.upper() not in VALID_STATUS:
        issues.append(f"solar_status must be one of {sorted(VALID_STATUS)}.")
    if reading.wind_status.upper() not in VALID_STATUS:
        issues.append(f"wind_status must be one of {sorted(VALID_STATUS)}.")
    if reading.generator_status is not None and reading.generator_status.upper() not in VALID_GEN:
        issues.append(f"generator_status has unrecognized value: {reading.generator_status!r}.")

    return issues
