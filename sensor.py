from __future__ import annotations

import time
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinjetCoordinator
from .models import MinjetDeviceDescriptor, as_float, battery_status_raw, battery_status_text, calculate_power_values, get_device_properties

DEBUG_SENSORS: list[
    tuple[str, str, str | None, SensorDeviceClass | None, SensorStateClass | None]
] = [
    ("connection_mode", "Connection Mode", None, None, None),
    ("websocket_connected", "WebSocket Connected", None, None, None),
    ("device_offline", "Device Offline", None, None, None),
    ("offline_minutes", "Offline Minutes", None, None, None),
]

RAW_SENSORS: list[
    tuple[str, str, str | None, SensorDeviceClass | None, SensorStateClass | None]
] = [
    ("photovoltaicPower", "PV Total Power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("outputPower", "Output Power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("batteryPower", "Battery Power Raw", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("batteryPercentage", "Battery Percentage", "%", SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT),
    ("temperature1", "Temperature 1", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    ("temperature2", "Temperature 2", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    ("cellVoltMax", "Cell Voltage Max", "mV", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
    ("cellVoltMin", "Cell Voltage Min", "mV", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
    ("WiFiRSSI", "WiFi RSSI", "dBm", None, SensorStateClass.MEASUREMENT),
    ("emFeedbackValue", "EM Feedback Value", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("batteryStatus", "Battery Status", None, None, None),
    ("batteryPriorityModeStatus", "Operation Mode", None, None, None),
    ("batteryChargeLimit", "Battery Charge Limit", "%", None, SensorStateClass.MEASUREMENT),
    ("batteryDischargeLimit", "Battery Discharge Limit", "%", None, SensorStateClass.MEASUREMENT),
    ("gridImportPower", "Grid Import Power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("gridExportPower", "Grid Export Power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("ratedPower", "Rated Power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
]

DERIVED_POWER_SENSORS: list[
    tuple[str, str, str | None, SensorDeviceClass | None, SensorStateClass | None]
] = [
    ("battery_charge_power", "Battery Charge Power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("battery_discharge_power", "Battery Discharge Power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("pv_to_inverter_power", "PV to Inverter Power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("battery_to_inverter_power", "Battery to Inverter Power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("pv_to_battery_power", "PV to Battery Power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("cell_voltage_delta", "Cell Voltage Delta", "mV", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
]

DERIVED_ENERGY_SENSORS: list[tuple[str, str]] = [
    ("solar_energy", "Solar Energy"),
    ("battery_charge_energy", "Battery Charge Energy"),
    ("battery_discharge_energy", "Battery Discharge Energy"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinjetCoordinator = hass.data[DOMAIN]["entries"][entry.entry_id]["coordinator"]

    entities: list[SensorEntity] = []
    for descriptor in coordinator.device_descriptors():
        entities.extend(
            MinjetRawSensor(
                coordinator,
                key,
                name,
                unit,
                device_class,
                state_class,
                descriptor,
            )
            for key, name, unit, device_class, state_class in RAW_SENSORS
        )

        entities.extend(
            MinjetDerivedPowerSensor(
                coordinator,
                key,
                name,
                unit,
                device_class,
                state_class,
                descriptor,
            )
            for key, name, unit, device_class, state_class in DERIVED_POWER_SENSORS
        )

        entities.extend(
            MinjetDerivedEnergySensor(
                coordinator,
                key,
                name,
                descriptor,
            )
            for key, name in DERIVED_ENERGY_SENSORS
        )

        entities.extend(
            MinjetDebugSensor(
                coordinator,
                key,
                name,
                unit,
                device_class,
                state_class,
                descriptor,
            )
            for key, name, unit, device_class, state_class in DEBUG_SENSORS
        )

    async_add_entities(entities)


class MinjetBaseSensor(CoordinatorEntity[MinjetCoordinator], SensorEntity):
    def __init__(
        self,
        coordinator: MinjetCoordinator,
        key: str,
        name: str,
        unit: str | None,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass | None,
        descriptor: MinjetDeviceDescriptor,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._serial_num = descriptor.serial_num
        self._attr_name = f"{descriptor.stable_name} {name}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_has_entity_name = False

        self._stable_device_id = descriptor.stable_device_id
        self._stable_serial = descriptor.stable_serial
        self._stable_name = descriptor.stable_name
        self._stable_model = descriptor.stable_model
        self._stable_sw_version = descriptor.stable_sw_version

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._stable_device_id)},
            name=self._stable_name,
            manufacturer="Minjet",
            model=self._stable_model,
            serial_number=self._stable_serial,
            sw_version=self._stable_sw_version,
        )

    @property
    def unique_id(self) -> str:
        return f"{self._stable_device_id}_{self._key}"

    @property
    def available(self) -> bool:
        return super().available and bool(self._device())

    def _device(self) -> dict[str, Any]:
        return self.coordinator.get_device(self._serial_num)

    def _properties(self) -> dict[str, Any]:
        return get_device_properties(self._device())

    def _connection(self) -> dict[str, Any]:
        return self._device().get("_connection", {}) or {}

    def _battery_status_raw(self) -> int | None:
        return battery_status_raw(self._properties())

    def _battery_status_text(self) -> str:
        return battery_status_text(self._properties())

    def _calc_values(self) -> dict[str, float]:
        return calculate_power_values(self._properties())


class MinjetRawSensor(MinjetBaseSensor):
    @property
    def native_value(self) -> Any:
        props = self._properties()

        if self._key == "batteryStatus":
            return self._battery_status_text()

        if self._key == "batteryPriorityModeStatus":
            value = props.get("batteryPriorityModeStatus")
            return {
                0: "erst entladen",
                1: "erst speichern",
            }.get(value, "unknown")

        if self._key == "gridImportPower":
            value = as_float(props.get("emFeedbackValue"))
            return abs(value) if value < 0 else 0.0

        if self._key == "gridExportPower":
            value = as_float(props.get("emFeedbackValue"))
            return value if value > 0 else 0.0

        return props.get(self._key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._key == "batteryStatus":
            return {"raw_value": self._battery_status_raw()}

        if self._key == "batteryPriorityModeStatus":
            return {"raw_value": self._properties().get("batteryPriorityModeStatus")}

        if self._key == "batteryDischargeLimit":
            return {"visible_in_mode": "erst speichern"}

        if self._key == "batteryChargeLimit":
            return {"visible_in_mode": "erst speichern"}

        else:
            return None


class MinjetDerivedPowerSensor(MinjetBaseSensor):
    @property
    def native_value(self) -> float | int:
        values = self._calc_values()

        mapping = {
            "battery_charge_power": values["battery_charge_power"],
            "battery_discharge_power": values["battery_discharge_power"],
            "pv_to_inverter_power": values["pv_to_inverter_power"],
            "battery_to_inverter_power": values["battery_to_inverter_power"],
            "pv_to_battery_power": values["pv_to_battery_power"],
            "cell_voltage_delta": values["cell_voltage_delta"],
        }

        return mapping.get(self._key, 0.0)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        values = self._calc_values()
        return {
            "battery_status": self._battery_status_text(),
            "battery_status_raw": self._battery_status_raw(),
            "photovoltaic_power_raw": values["photovoltaic_power"],
            "output_power_raw": values["output_power"],
            "battery_power_raw": values["battery_power"],
        }


class MinjetDebugSensor(MinjetBaseSensor):
    @property
    def native_value(self) -> Any:
        connection = self._connection()

        if self._key == "connection_mode":
            if connection.get("device_offline", False):
                return "Offline"
            if not connection.get("websocket_enabled", False):
                return "REST"
            if connection.get("websocket_connected", False):
                return "WebSocket"
            return "REST fallback"

        if self._key == "websocket_connected":
            return connection.get("websocket_connected", False)

        if self._key == "device_offline":
            return connection.get("device_offline", False)

        if self._key == "offline_minutes":
            offline_since = connection.get("offline_since")
            if not offline_since:
                return 0
            return int((time.time() - offline_since) / 60)

        return None


class MinjetDerivedEnergySensor(MinjetBaseSensor, RestoreEntity):
    def __init__(
        self,
        coordinator: MinjetCoordinator,
        key: str,
        name: str,
        descriptor: MinjetDeviceDescriptor,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            key=key,
            name=name,
            unit="kWh",
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            descriptor=descriptor,
        )
        self._energy_kwh: float = 0.0
        self._last_update_ts: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable"):
            try:
                self._energy_kwh = float(last_state.state)
            except (TypeError, ValueError):
                self._energy_kwh = 0.0

    @property
    def native_value(self) -> float:
        return round(self._energy_kwh, 4)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return {
            "source": "integrated_from_power",
            "last_update_ts": self._last_update_ts,
        }

    def _handle_coordinator_update(self) -> None:
        props = self._properties()
        current_time = as_float(props.get("currentTime"))

        if current_time <= 0:
            super()._handle_coordinator_update()
            return

        values = self._calc_values()

        power_w = 0.0
        if self._key == "solar_energy":
            power_w = max(values["photovoltaic_power"], 0.0)
        elif self._key == "battery_charge_energy":
            power_w = max(values["battery_charge_power"], 0.0)
        elif self._key == "battery_discharge_energy":
            power_w = max(values["battery_discharge_power"], 0.0)

        if self._last_update_ts is not None and current_time > self._last_update_ts:
            delta_seconds = current_time - self._last_update_ts
            self._energy_kwh += (power_w * delta_seconds) / 3600000.0

        self._last_update_ts = current_time
        super()._handle_coordinator_update()
