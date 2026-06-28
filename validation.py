from __future__ import annotations

from .const import (
    BATTERY_DISCHARGE_LIMIT_STEP,
    MAX_BATTERY_DISCHARGE_LIMIT,
    MAX_RATED_POWER,
    MIN_BATTERY_DISCHARGE_LIMIT,
    MIN_RATED_POWER,
    MODE_FIRST_DISCHARGE,
    MODE_FIRST_STORE,
)


def coerce_rated_power(value: object) -> int:
    try:
        rated_power = int(value)
    except (TypeError, ValueError) as err:
        raise ValueError("rated_power must be an integer") from err

    if rated_power < MIN_RATED_POWER or rated_power > MAX_RATED_POWER:
        raise ValueError(
            f"rated_power must be between {MIN_RATED_POWER} and {MAX_RATED_POWER}"
        )

    return rated_power


def coerce_battery_discharge_limit(value: object) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError) as err:
        raise ValueError("battery_discharge_limit must be an integer") from err

    if limit < MIN_BATTERY_DISCHARGE_LIMIT or limit > MAX_BATTERY_DISCHARGE_LIMIT:
        raise ValueError(
            f"battery_discharge_limit must be between "
            f"{MIN_BATTERY_DISCHARGE_LIMIT} and {MAX_BATTERY_DISCHARGE_LIMIT}"
        )

    if limit % BATTERY_DISCHARGE_LIMIT_STEP != 0:
        raise ValueError(
            f"battery_discharge_limit must use {BATTERY_DISCHARGE_LIMIT_STEP}-point steps"
        )

    return limit


def coerce_operation_mode(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("operation_mode must be a string")

    normalized = value.strip().lower().replace(" ", "_")
    if normalized not in (MODE_FIRST_DISCHARGE, MODE_FIRST_STORE):
        raise ValueError(
            f"operation_mode must be '{MODE_FIRST_DISCHARGE}' or '{MODE_FIRST_STORE}'"
        )

    return normalized
