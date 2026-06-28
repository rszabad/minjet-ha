from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_BATTERY_DISCHARGE_LIMIT,
    ATTR_OPERATION_MODE,
    ATTR_RATED_POWER,
    ATTR_SERIAL_NUM,
    DOMAIN,
    MODE_FIRST_DISCHARGE,
    MODE_FIRST_STORE,
    SERVICE_SET_BATTERY_DISCHARGE_LIMIT,
    SERVICE_SET_OPERATION_MODE,
    SERVICE_SET_RATED_POWER,
)
from .validation import (
    coerce_battery_discharge_limit,
    coerce_operation_mode,
    coerce_rated_power,
)

SERVICE_SET_OPERATION_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SERIAL_NUM): cv.string,
        vol.Required(ATTR_OPERATION_MODE): coerce_operation_mode,
    }
)

SERVICE_SET_BATTERY_DISCHARGE_LIMIT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SERIAL_NUM): cv.string,
        vol.Required(ATTR_BATTERY_DISCHARGE_LIMIT): coerce_battery_discharge_limit,
    }
)

SERVICE_SET_RATED_POWER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SERIAL_NUM): cv.string,
        vol.Required(ATTR_RATED_POWER): coerce_rated_power,
    }
)

MODE_TO_API_VALUE = {
    MODE_FIRST_DISCHARGE: 0,
    MODE_FIRST_STORE: 1,
}


def _resolve_entry_data(hass: HomeAssistant, serial_num: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for entry_data in hass.data.get(DOMAIN, {}).get("entries", {}).values():
        coordinator = entry_data["coordinator"]
        if any(descriptor.serial_num == serial_num for descriptor in coordinator.device_descriptors()):
            matches.append(entry_data)

    if not matches:
        raise HomeAssistantError(f"Unknown Minjet device serial: {serial_num}")
    if len(matches) > 1:
        raise HomeAssistantError(f"Serial number is ambiguous across Minjet entries: {serial_num}")

    return matches[0]


async def async_register_services(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("services_registered"):
        return

    async def handle_set_operation_mode(service_call: ServiceCall) -> None:
        serial_num = service_call.data[ATTR_SERIAL_NUM]
        operation_mode = service_call.data[ATTR_OPERATION_MODE]
        entry_data = _resolve_entry_data(hass, serial_num)
        await entry_data["api"].async_set_operation_mode(
            serial_num,
            MODE_TO_API_VALUE[operation_mode],
        )
        await entry_data["coordinator"].async_request_refresh()

    async def handle_set_battery_discharge_limit(service_call: ServiceCall) -> None:
        serial_num = service_call.data[ATTR_SERIAL_NUM]
        discharge_limit = service_call.data[ATTR_BATTERY_DISCHARGE_LIMIT]
        entry_data = _resolve_entry_data(hass, serial_num)
        await entry_data["api"].async_set_battery_discharge_limit(serial_num, discharge_limit)
        await entry_data["coordinator"].async_request_refresh()

    async def handle_set_rated_power(service_call: ServiceCall) -> None:
        serial_num = service_call.data[ATTR_SERIAL_NUM]
        rated_power = service_call.data[ATTR_RATED_POWER]
        entry_data = _resolve_entry_data(hass, serial_num)
        await entry_data["api"].async_set_rated_power(serial_num, rated_power)
        await entry_data["coordinator"].async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_OPERATION_MODE,
        handle_set_operation_mode,
        schema=SERVICE_SET_OPERATION_MODE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BATTERY_DISCHARGE_LIMIT,
        handle_set_battery_discharge_limit,
        schema=SERVICE_SET_BATTERY_DISCHARGE_LIMIT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_RATED_POWER,
        handle_set_rated_power,
        schema=SERVICE_SET_RATED_POWER_SCHEMA,
    )
    domain_data["services_registered"] = True


async def async_unregister_services(hass: HomeAssistant) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    if domain_data.get("entries"):
        return

    for service_name in (
        SERVICE_SET_OPERATION_MODE,
        SERVICE_SET_BATTERY_DISCHARGE_LIMIT,
        SERVICE_SET_RATED_POWER,
    ):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)

    domain_data["services_registered"] = False
