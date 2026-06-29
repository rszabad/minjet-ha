"""Minjet zero-export control example for Home Assistant pyscript.

Requires pyscript with:
  allow_all_imports: true
"""

from collections import deque

from custom_components.minjet.zero_export import (
    evaluate_zero_export_cycle,
    normalize_grid_power,
    parse_float_state,
    resolve_last_setpoint,
)

MINJET_SERIAL = "MH7A482403200216"
GRID_POWER_ENTITY = "sensor.grid_power"
GRID_SIGN = 1
DEVICE_OFFLINE_ENTITY = "sensor.mh7a_48_robert_device_offline"
SOC_ENTITY = ""

CONTROL_INTERVAL_SECONDS = 10

HELPER_ENABLED = "input_boolean.zero_export_enabled"
HELPER_MIN_POWER = "input_number.zero_export_min_power"
HELPER_MAX_POWER = "input_number.zero_export_max_power"
HELPER_DEADBAND = "input_number.zero_export_deadband"
HELPER_STEP_LIMIT = "input_number.zero_export_step_limit"
HELPER_LAST_SETPOINT = "input_number.zero_export_last_setpoint"
HELPER_MIN_WRITE_DELTA = "input_number.zero_export_min_write_delta"

STATUS_ACTIVE = "pyscript.minjet_zero_export_active"
STATUS_BLOCK_REASON = "pyscript.minjet_zero_export_block_reason"
STATUS_LAST_GRID_POWER = "pyscript.minjet_zero_export_last_grid_power"
STATUS_LAST_TARGET = "pyscript.minjet_zero_export_last_target"
STATUS_LAST_WRITE_TS = "pyscript.minjet_zero_export_last_write_ts"

task.unique("minjet_zero_export_script")

_grid_history = deque(maxlen=2)


def _safe_state_get(entity_id):
    if not entity_id:
        return None
    try:
        return state.get(entity_id)
    except Exception:
        return None


def _get_bool(entity_id, default=False):
    value = _safe_state_get(entity_id)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "on", "true", "yes"}


def _get_int(entity_id, default):
    value = parse_float_state(_safe_state_get(entity_id))
    if value is None:
        return default
    return int(round(value))


def _set_status(active, block_reason="", last_grid_power=None, last_target=None, last_write_ts=None):
    state.set(STATUS_ACTIVE, value="on" if active else "off")
    state.set(STATUS_BLOCK_REASON, value=block_reason or "")

    if last_grid_power is None:
        state.set(STATUS_LAST_GRID_POWER, value="unknown")
    else:
        state.set(STATUS_LAST_GRID_POWER, value=round(last_grid_power, 1))

    if last_target is not None:
        state.set(STATUS_LAST_TARGET, value=int(last_target))

    if last_write_ts is not None:
        state.set(STATUS_LAST_WRITE_TS, value=str(last_write_ts))


def _persist_status_entities():
    state.persist(STATUS_ACTIVE, default_value="off")
    state.persist(STATUS_BLOCK_REASON, default_value="disabled")
    state.persist(STATUS_LAST_GRID_POWER, default_value="unknown")
    state.persist(STATUS_LAST_TARGET, default_value="0")
    state.persist(STATUS_LAST_WRITE_TS, default_value="")


def _current_limits():
    min_power = _get_int(HELPER_MIN_POWER, 0)
    max_power = _get_int(HELPER_MAX_POWER, 800)
    if min_power > max_power:
        min_power, max_power = max_power, min_power
    return min_power, max_power


def _device_offline():
    if not DEVICE_OFFLINE_ENTITY:
        return False
    return _get_bool(DEVICE_OFFLINE_ENTITY, default=False)


@time_trigger("startup")
def minjet_zero_export_init():
    _persist_status_entities()
    min_power, max_power = _current_limits()
    last_target = resolve_last_setpoint(_safe_state_get(HELPER_LAST_SETPOINT), min_power, max_power)
    _set_status(active=False, block_reason="disabled", last_target=last_target)


@time_trigger(f"period(now + {CONTROL_INTERVAL_SECONDS}s, {CONTROL_INTERVAL_SECONDS}s)")
def minjet_zero_export_cycle(trigger_time=None):
    task.unique("minjet_zero_export_cycle", kill_me=True)

    min_power, max_power = _current_limits()
    deadband = _get_int(HELPER_DEADBAND, 30)
    step_limit = _get_int(HELPER_STEP_LIMIT, 100)
    min_write_delta = _get_int(HELPER_MIN_WRITE_DELTA, 30)
    old_target = resolve_last_setpoint(_safe_state_get(HELPER_LAST_SETPOINT), min_power, max_power)
    raw_grid_power = _safe_state_get(GRID_POWER_ENTITY)

    normalized_grid_power = normalize_grid_power(raw_grid_power, GRID_SIGN)
    if normalized_grid_power is not None:
        _grid_history.append(normalized_grid_power)

    decision = evaluate_zero_export_cycle(
        enabled=_get_bool(HELPER_ENABLED, default=False),
        device_offline=_device_offline(),
        raw_grid_power=raw_grid_power,
        grid_sign=GRID_SIGN,
        old_target=old_target,
        deadband=deadband,
        step_limit=step_limit,
        min_power=min_power,
        max_power=max_power,
        min_write_delta=min_write_delta,
        recent_grid_powers=list(_grid_history),
    )

    _set_status(
        active=decision.active,
        block_reason=decision.block_reason or "",
        last_grid_power=decision.averaged_grid_power,
        last_target=decision.next_target,
    )

    if not decision.should_write:
        return

    try:
        service.call(
            "minjet",
            "set_rated_power",
            blocking=True,
            serial_num=MINJET_SERIAL,
            rated_power=decision.next_target,
        )
        service.call(
            "input_number",
            "set_value",
            blocking=True,
            entity_id=HELPER_LAST_SETPOINT,
            value=decision.next_target,
        )
    except Exception as err:
        _set_status(
            active=False,
            block_reason="write_failed",
            last_grid_power=decision.averaged_grid_power,
            last_target=old_target,
        )
        log.warning(f"minjet zero export write failed: {err}")
        return

    _set_status(
        active=True,
        block_reason="",
        last_grid_power=decision.averaged_grid_power,
        last_target=decision.next_target,
        last_write_ts=trigger_time,
    )
