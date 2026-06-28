from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    DEVICE_LIST_ENDPOINT,
    DEVICE_PARAM_ENDPOINT,
    LOGIN_ENDPOINT,
    PHOTOVOLTAIC_QUERY_ENDPOINT,
    SET_RATED_POWER_ENDPOINT,
    SET_STACKING_PROPERTY_ENDPOINT,
    STACKING_QUERY_ENDPOINT,
    TOKEN_REFRESH_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class MinjetApiError(Exception):
    """Base API error."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.data = data


class MinjetAuthError(MinjetApiError):
    """Authentication error."""


class MinjetApi:
    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._token_acquired_at: float | None = None
        self._token_generation = 0
        self._auth_lock = asyncio.Lock()

    async def async_login(self) -> str:
        payload = {
            "username": self._username,
            "password": self._password,
        }

        _LOGGER.debug("Minjet login request starting for user: %s", self._username)
        resp, data, _text = await self._request_json(
            "POST",
            LOGIN_ENDPOINT,
            json_body=payload,
            authenticated=False,
            retry_auth=False,
        )

        token = data.get("token")
        if resp.status != 200 or data.get("code") != 200 or not isinstance(token, str) or not token.strip():
            raise MinjetAuthError(f"Login failed: {data}")

        self._token = token.strip()
        self._token_acquired_at = time.time()
        self._token_generation += 1
        _LOGGER.debug("Minjet token acquired, length=%s", len(self._token))
        return self._token

    @property
    def session(self) -> aiohttp.ClientSession:
        return self._session

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def token_generation(self) -> int:
        return self._token_generation

    def token_needs_refresh(self) -> bool:
        return self._token_needs_refresh()

    def _token_needs_refresh(self) -> bool:
        if not self._token:
            return True
        if not self._token_acquired_at:
            return True
        age_seconds = time.time() - self._token_acquired_at
        return age_seconds >= TOKEN_REFRESH_INTERVAL_SECONDS

    async def _ensure_valid_token(self, force_refresh: bool = False) -> str:
        if not force_refresh and not self._token_needs_refresh():
            token = self._token
            if isinstance(token, str) and token.strip():
                return token

        async with self._auth_lock:
            if not force_refresh and not self._token_needs_refresh():
                token = self._token
                if isinstance(token, str) and token.strip():
                    return token
            return await self.async_login()

    async def async_refresh_token(self, force_refresh: bool = False) -> str:
        return await self._ensure_valid_token(force_refresh=force_refresh)

    async def async_get_devices(self) -> list[dict[str, Any]]:
        data = await self._api_get(DEVICE_LIST_ENDPOINT, "device query")
        devices = data.get("data", [])
        if not isinstance(devices, list):
            raise MinjetApiError(f"Unexpected response: {data}")
        return devices

    async def async_get_device_param(self, serial_num: str) -> dict[str, Any]:
        data = await self._api_get(
            f"{DEVICE_PARAM_ENDPOINT}?serialNumber={serial_num}",
            f"device param query for {serial_num}",
        )
        payload = data.get("data", {})
        return payload if isinstance(payload, dict) else {}

    async def async_get_stacking(self, serial_num: str, realtime_status: int = 1) -> dict[str, Any]:
        data = await self._api_get(
            f"{STACKING_QUERY_ENDPOINT}/{serial_num}/{realtime_status}",
            f"stacking query for {serial_num}",
        )
        payload = data.get("data", {})
        return payload if isinstance(payload, dict) else {}

    async def async_get_photovoltaic(self, serial_num: str) -> dict[str, Any]:
        data = await self._api_get(
            f"{PHOTOVOLTAIC_QUERY_ENDPOINT}/{serial_num}",
            f"photovoltaic query for {serial_num}",
        )
        payload = data.get("data", {})
        return payload if isinstance(payload, dict) else {}

    async def async_set_rated_power(self, serial_num: str, value: int | float) -> Any:
        data = await self._api_post(
            f"{SET_RATED_POWER_ENDPOINT}/{serial_num}",
            {
                "key": "ratedPower",
                "orderCode": "",
                "value": value,
            },
            f"set rated power for {serial_num}",
        )
        return data.get("data")

    async def async_set_operation_mode(self, serial_num: str, mode_value: int) -> Any:
        return await self.async_set_stacking_property(
            serial_num,
            "batteryPriorityModeStatus",
            mode_value,
            verify_readback=True,
        )

    async def async_set_battery_discharge_limit(self, serial_num: str, value: int) -> Any:
        return await self.async_set_stacking_property(
            serial_num,
            "batteryDischargeLimit",
            value,
            verify_readback=True,
        )

    async def async_set_stacking_property(
        self,
        serial_num: str,
        key: str,
        value: Any,
        order_code: str = "",
        verify_readback: bool = False,
    ) -> Any:
        payload = {
            "key": key,
            "orderCode": order_code,
            "value": value,
        }

        try:
            data = await self._api_post(
                f"{SET_STACKING_PROPERTY_ENDPOINT}/{serial_num}",
                payload,
                f"set stacking property {key} for {serial_num}",
            )
            return data.get("data")
        except MinjetApiError as err:
            if not verify_readback or err.status != 504:
                raise

        await asyncio.sleep(5)
        current = await self.async_get_device_param(serial_num)
        if current.get(key) == value:
            return value

        raise MinjetApiError(
            f"Minjet stacking write for {serial_num} timed out and verification failed",
            status=504,
            data={"key": key, "value": value},
        )

    async def async_test_credentials(self) -> None:
        await self.async_login()
        await self.async_get_devices()

    async def _api_get(self, url: str, context: str) -> dict[str, Any]:
        _LOGGER.debug("Minjet %s starting with GET", context)
        _resp, data, _text = await self._request_json("GET", url)
        self._validate_api_response(data, context)
        return data

    async def _api_post(self, url: str, payload: dict[str, Any], context: str) -> dict[str, Any]:
        _LOGGER.debug("Minjet %s starting with POST", context)
        _resp, data, _text = await self._request_json("POST", url, json_body=payload)
        self._validate_api_response(data, context)
        return data

    async def _request_json(
        self,
        method: str,
        url: str,
        json_body: dict[str, Any] | None = None,
        authenticated: bool = True,
        retry_auth: bool = True,
    ) -> tuple[aiohttp.ClientResponse, dict[str, Any], str]:
        attempts = 2 if authenticated and retry_auth else 1

        for attempt in range(1, attempts + 1):
            headers: dict[str, str] = {}
            if authenticated:
                force_refresh = attempt > 1
                await self._ensure_valid_token(force_refresh=force_refresh)

                if not isinstance(self._token, str) or not self._token.strip():
                    raise MinjetAuthError(f"Token invalid after login: {self._token!r}")

                headers["Authorization"] = f"Bearer {self._token}"

            requester = self._session.get if method.upper() == "GET" else self._session.post
            kwargs: dict[str, Any] = {
                "headers": headers,
                "timeout": 20,
            }
            if json_body is not None:
                kwargs["json"] = json_body

            async with requester(url, **kwargs) as resp:
                text = await resp.text()

            try:
                data = json.loads(text)
            except Exception as err:
                raise MinjetApiError(f"Request returned non-JSON for {url}: {text}") from err

            if authenticated and resp.status in (401, 403):
                _LOGGER.warning("Minjet request returned %s for %s", resp.status, url)
                self._token = None
                self._token_acquired_at = None
                if attempt < attempts:
                    continue
                raise MinjetAuthError(f"Unauthorized ({resp.status})")

            if 400 <= resp.status < 500:
                raise MinjetApiError(
                    f"Client error {resp.status} for {url}: {data}",
                    status=resp.status,
                    data=data,
                )

            if resp.status >= 500:
                raise MinjetApiError(
                    f"Server error {resp.status} for {url}: {data}",
                    status=resp.status,
                    data=data,
                )

            return resp, data, text

        raise MinjetAuthError("Unable to refresh token")

    def _validate_api_response(self, data: dict[str, Any], context: str) -> None:
        if data.get("code") != 200:
            raise MinjetApiError(f"Minjet {context} failed: {data}")
