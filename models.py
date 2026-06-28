from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class MinjetDeviceDescriptor:
    serial_num: str
    stable_device_id: str
    stable_serial: str
    stable_name: str
    stable_model: str
    stable_sw_version: str | None


def get_device_serial(device: Mapping[str, Any]) -> str | None:
    for key in ("serialNum", "serialNumber", "deviceName"):
        value = device.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def build_device_descriptor(device: Mapping[str, Any]) -> MinjetDeviceDescriptor | None:
    serial_num = get_device_serial(device)
    if not serial_num:
        return None

    stable_device_id = str(device.get("deviceId") or serial_num)
    stable_serial = str(device.get("serialNum") or stable_device_id)
    stable_name = str(device.get("customName") or device.get("deviceName") or stable_serial)
    stable_model = str(device.get("productCode") or device.get("productTypeCode") or "Minjet")
    stable_sw_version = device.get("deviceCurrentVersion")

    return MinjetDeviceDescriptor(
        serial_num=serial_num,
        stable_device_id=stable_device_id,
        stable_serial=stable_serial,
        stable_name=stable_name,
        stable_model=stable_model,
        stable_sw_version=stable_sw_version if isinstance(stable_sw_version, str) else None,
    )


def normalize_devices(devices: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for device in devices:
        serial_num = get_device_serial(device)
        if not serial_num:
            continue
        normalized[serial_num] = dict(device)
    return normalized


def get_device_properties(device: Mapping[str, Any] | None) -> dict[str, Any]:
    if not device:
        return {}
    props = device.get("properties")
    return dict(props) if isinstance(props, Mapping) else {}


def battery_status_raw(properties: Mapping[str, Any]) -> int | None:
    value = properties.get("batteryStatus")
    return value if isinstance(value, int) else None


def battery_status_text(properties: Mapping[str, Any]) -> str:
    return {
        0: "Idle",
        1: "Charging",
        2: "Discharging",
    }.get(battery_status_raw(properties), "Unknown")


def calculate_power_values(properties: Mapping[str, Any]) -> dict[str, float]:
    photovoltaic_power = as_float(properties.get("photovoltaicPower"))
    output_power = as_float(properties.get("outputPower"))
    battery_power = as_float(properties.get("batteryPower"))
    cell_volt_max = as_float(properties.get("cellVoltMax"))
    cell_volt_min = as_float(properties.get("cellVoltMin"))
    status = battery_status_raw(properties)

    battery_charge_power = 0.0
    battery_discharge_power = 0.0
    pv_to_inverter_power = 0.0
    pv_to_battery_power = 0.0
    battery_to_inverter_power = 0.0

    if status == 1:
        battery_charge_power = max(battery_power, 0.0)
        pv_to_battery_power = battery_charge_power
        pv_to_inverter_power = max(output_power, 0.0)
    elif status == 2:
        battery_discharge_power = max(battery_power, 0.0)
        battery_to_inverter_power = battery_discharge_power
        pv_to_inverter_power = max(photovoltaic_power, 0.0)
    else:
        pv_to_inverter_power = max(min(photovoltaic_power, output_power), 0.0)

    return {
        "photovoltaic_power": photovoltaic_power,
        "output_power": output_power,
        "battery_power": battery_power,
        "battery_charge_power": round(battery_charge_power, 1),
        "battery_discharge_power": round(battery_discharge_power, 1),
        "pv_to_inverter_power": round(pv_to_inverter_power, 1),
        "pv_to_battery_power": round(pv_to_battery_power, 1),
        "battery_to_inverter_power": round(battery_to_inverter_power, 1),
        "cell_voltage_delta": round(max(cell_volt_max - cell_volt_min, 0.0), 1),
    }


def resolve_ws_target_serial(payload_data: Mapping[str, Any], known_serials: set[str]) -> str | None:
    for key in ("serialNum", "serialNumber", "deviceName"):
        value = payload_data.get(key)
        if isinstance(value, str) and value in known_serials:
            return value

    if len(known_serials) == 1:
        return next(iter(known_serials))

    return None


def as_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
