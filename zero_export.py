from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

INVALID_STATE_VALUES = {"", "none", "null", "unknown", "unavailable"}


@dataclass(frozen=True)
class ZeroExportDecision:
    active: bool
    block_reason: str | None
    averaged_grid_power: float | None
    next_target: int
    should_write: bool


def clamp_target(value: int | float, min_power: int, max_power: int) -> int:
    return int(round(max(min_power, min(max_power, value))))


def parse_float_state(value: object) -> float | None:
    if value is None:
        return None

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in INVALID_STATE_VALUES:
            return None
        value = normalized

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_grid_power(raw_value: object, grid_sign: int) -> float | None:
    if grid_sign not in (-1, 1):
        raise ValueError("grid_sign must be -1 or 1")

    value = parse_float_state(raw_value)
    if value is None:
        return None

    return value * grid_sign


def average_recent_grid_powers(values: Sequence[float], limit: int = 2) -> float | None:
    if limit <= 0:
        raise ValueError("limit must be positive")

    recent = [float(value) for value in values[-limit:]]
    if not recent:
        return None

    return sum(recent) / len(recent)


def resolve_last_setpoint(
    helper_value: object,
    min_power: int,
    max_power: int,
    default_value: int = 0,
) -> int:
    parsed = parse_float_state(helper_value)
    if parsed is None:
        return clamp_target(default_value, min_power, max_power)
    return clamp_target(parsed, min_power, max_power)


def compute_next_target(
    old_target: int,
    grid_power: float,
    deadband: int,
    step_limit: int,
    min_power: int,
    max_power: int,
    min_write_delta: int,
) -> tuple[int, bool, str | None]:
    if deadband < 0:
        raise ValueError("deadband must be >= 0")
    if step_limit < 0:
        raise ValueError("step_limit must be >= 0")
    if min_write_delta < 0:
        raise ValueError("min_write_delta must be >= 0")
    if min_power > max_power:
        raise ValueError("min_power must be <= max_power")

    clamped_old_target = clamp_target(old_target, min_power, max_power)

    if abs(grid_power) <= deadband:
        return clamped_old_target, False, "within_deadband"

    limited_delta = max(-step_limit, min(step_limit, grid_power))
    candidate = clamp_target(clamped_old_target + limited_delta, min_power, max_power)

    if abs(candidate - clamped_old_target) < min_write_delta:
        return candidate, False, "delta_too_small"

    return candidate, True, None


def evaluate_zero_export_cycle(
    *,
    enabled: bool,
    device_offline: bool,
    raw_grid_power: object,
    grid_sign: int,
    old_target: int,
    deadband: int,
    step_limit: int,
    min_power: int,
    max_power: int,
    min_write_delta: int,
    recent_grid_powers: Sequence[float] | None = None,
) -> ZeroExportDecision:
    clamped_old_target = clamp_target(old_target, min_power, max_power)

    if not enabled:
        return ZeroExportDecision(False, "disabled", None, clamped_old_target, False)

    if device_offline:
        return ZeroExportDecision(False, "device_offline", None, clamped_old_target, False)

    normalized_grid_power = normalize_grid_power(raw_grid_power, grid_sign)
    if normalized_grid_power is None:
        return ZeroExportDecision(False, "grid_unavailable", None, clamped_old_target, False)

    averaged_grid_power = average_recent_grid_powers(
        list(recent_grid_powers or ()) or [normalized_grid_power],
        limit=2,
    )
    assert averaged_grid_power is not None

    next_target, should_write, block_reason = compute_next_target(
        old_target=clamped_old_target,
        grid_power=averaged_grid_power,
        deadband=deadband,
        step_limit=step_limit,
        min_power=min_power,
        max_power=max_power,
        min_write_delta=min_write_delta,
    )

    return ZeroExportDecision(
        True,
        block_reason,
        averaged_grid_power,
        next_target,
        should_write,
    )
