from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any, Iterable

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MinjetApi
from .const import DEFAULT_SCAN_INTERVAL, MIN_SCAN_INTERVAL
from .models import MinjetDeviceDescriptor, build_device_descriptor, normalize_devices, resolve_ws_target_serial
from .websocket import MinjetWebSocketClient

_LOGGER = logging.getLogger(__name__)


class MinjetCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass,
        api: MinjetApi,
        enable_websocket: bool = False,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ):
        try:
            scan_interval = int(scan_interval)
        except (TypeError, ValueError):
            scan_interval = DEFAULT_SCAN_INTERVAL
        scan_interval = max(MIN_SCAN_INTERVAL, scan_interval)
        super().__init__(
            hass,
            _LOGGER,
            name="Minjet",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self._enable_websocket = enable_websocket

        self._rest_devices: dict[str, dict[str, Any]] = {}
        self._wss_devices: dict[str, dict[str, Any]] = {}
        self._device_descriptors: dict[str, MinjetDeviceDescriptor] = {}
        self._known_serials: set[str] = set()
        self._offline_since_by_serial: dict[str, float | None] = {}
        self._wss_connected = False

        self._ws_client: MinjetWebSocketClient | None = None

    async def async_setup(self) -> None:
        if not self._rest_devices:
            devices = await self.api.async_get_devices()
            self._rest_devices = normalize_devices(devices)
            self._update_descriptors(self._rest_devices.values())
            self._known_serials.update(self._rest_devices)

        if self._enable_websocket:
            await self._start_websocket()

    async def _start_websocket(self) -> None:
        try:
            if self._ws_client:
                return

            token = self.api.token
            if not token:
                _LOGGER.debug("No token for WSS")
                return

            self._ws_client = MinjetWebSocketClient(
                session=self.api.session,
                token=token,
                on_message=self._handle_wss_message,
                on_connected=self._handle_wss_connected,
                on_disconnected=self._handle_wss_disconnected,
            )
            await self._ws_client.start()
        except Exception as err:
            _LOGGER.error("Failed to start WSS: %s", err)

    async def _stop_websocket(self) -> None:
        if self._ws_client:
            await self._ws_client.stop()
            self._ws_client = None
        self._wss_connected = False
        self._wss_devices = {}

    async def _restart_websocket(self) -> None:
        await self._stop_websocket()
        await self._start_websocket()

    async def _handle_wss_connected(self) -> None:
        self._wss_connected = True
        self.async_set_updated_data(self._build_coordinator_data())

    async def _handle_wss_disconnected(self) -> None:
        self._wss_connected = False
        self._wss_devices = {}
        self.async_set_updated_data(self._build_coordinator_data())

    async def _handle_wss_message(self, payload: dict[str, Any]) -> None:
        data = payload.get("data")
        if not isinstance(data, dict):
            return

        serial_num = resolve_ws_target_serial(data, self._known_serials)
        if not serial_num:
            _LOGGER.debug("Skipping WebSocket payload because no device could be identified")
            return

        current = self._rest_devices.get(serial_num, {})
        merged = {
            **current,
            **data,
        }
        merged["properties"] = {
            **(current.get("properties") or {}),
            **(data.get("properties") or {}),
        }

        self._wss_devices[serial_num] = merged
        self._wss_connected = True
        self.async_set_updated_data(self._build_coordinator_data())

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            ws_restarted_for_token = False
            if self._enable_websocket and self._ws_client and self.api.token_needs_refresh():
                _LOGGER.debug("Token exceeded refresh interval; reconnecting WebSocket with fresh token")
                await self._stop_websocket()
                await self.api.async_refresh_token(force_refresh=True)
                await self._start_websocket()
                ws_restarted_for_token = True

            token_generation_before = self.api.token_generation
            devices = await self.api.async_get_devices()
            token_was_refreshed = self.api.token_generation != token_generation_before

            current_rest_devices = normalize_devices(devices)
            self._update_descriptors(current_rest_devices.values())

            for serial_num in current_rest_devices:
                self._known_serials.add(serial_num)

            merged_rest_devices = dict(self._rest_devices)
            now = time.time()

            for serial_num in self._known_serials:
                latest = current_rest_devices.get(serial_num)
                if latest is None:
                    self._offline_since_by_serial[serial_num] = self._offline_since_by_serial.get(serial_num) or now
                    continue

                if latest.get("properties") is None:
                    _LOGGER.debug("Device %s is offline", serial_num)
                    self._offline_since_by_serial[serial_num] = self._offline_since_by_serial.get(serial_num) or now
                    if serial_num not in merged_rest_devices:
                        merged_rest_devices[serial_num] = latest
                    continue

                merged_rest_devices[serial_num] = latest
                self._offline_since_by_serial[serial_num] = None

            self._rest_devices = merged_rest_devices

            if self._enable_websocket:
                if token_was_refreshed and self._ws_client and not ws_restarted_for_token:
                    _LOGGER.debug("Token refreshed during REST update; reconnecting WebSocket")
                    await self._restart_websocket()
                elif not self._ws_client:
                    await self._start_websocket()
                elif self.api.token:
                    self._ws_client.set_token(self.api.token)

            return self._build_coordinator_data()
        except Exception as err:
            _LOGGER.error("REST update failed: %s", err)
            raise UpdateFailed(f"REST update failed: {err}") from err

    def device_descriptors(self) -> list[MinjetDeviceDescriptor]:
        return list(self._device_descriptors.values())

    def get_device(self, serial_num: str) -> dict[str, Any]:
        devices = (self.data or {}).get("devices", {})
        device = devices.get(serial_num)
        return device if isinstance(device, dict) else {}

    def _build_coordinator_data(self) -> dict[str, Any]:
        devices: dict[str, dict[str, Any]] = {}
        now = time.time()

        for serial_num in self._known_serials:
            base = dict(self._rest_devices.get(serial_num, {}))
            ws_data = self._wss_devices.get(serial_num)

            if ws_data:
                base = {
                    **base,
                    **ws_data,
                    "properties": {
                        **(base.get("properties") or {}),
                        **(ws_data.get("properties") or {}),
                    },
                }

            offline_since = self._offline_since_by_serial.get(serial_num)
            device_offline = offline_since is not None
            last_update_source = "websocket" if ws_data and self._wss_connected else "rest"

            if not base:
                descriptor = self._device_descriptors.get(serial_num)
                if descriptor:
                    base = {
                        "serialNum": descriptor.serial_num,
                        "deviceId": descriptor.stable_device_id,
                        "deviceName": descriptor.stable_serial,
                        "customName": descriptor.stable_name,
                        "productCode": descriptor.stable_model,
                        "deviceCurrentVersion": descriptor.stable_sw_version,
                    }

            base["_connection"] = {
                "websocket_enabled": self._enable_websocket,
                "websocket_connected": self._wss_connected,
                "last_update_source": last_update_source,
                "device_offline": device_offline,
                "offline_since": offline_since or now if device_offline else None,
            }
            devices[serial_num] = base

        return {"devices": devices}

    def _update_descriptors(self, devices: Iterable[dict[str, Any]]) -> None:
        for device in devices:
            descriptor = build_device_descriptor(device)
            if descriptor:
                self._device_descriptors[descriptor.serial_num] = descriptor
