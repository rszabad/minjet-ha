from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from tests.support import import_minjet_module

if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")
    aiohttp_stub.ClientSession = object
    aiohttp_stub.ClientResponse = object
    sys.modules["aiohttp"] = aiohttp_stub

api_module = import_minjet_module("api")
MinjetApi = api_module.MinjetApi
MinjetApiError = api_module.MinjetApiError
MinjetAuthError = api_module.MinjetAuthError


class FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body

    async def text(self) -> str:
        return self._body

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeSession:
    def __init__(self, responses: list[tuple[int, dict | str]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append({"method": "GET", "url": url, "kwargs": kwargs})
        return self._next_response()

    def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, "kwargs": kwargs})
        return self._next_response()

    def _next_response(self) -> FakeResponse:
        if not self._responses:
            raise AssertionError("No fake response queued")
        status, body = self._responses.pop(0)
        if isinstance(body, str):
            text = body
        else:
            text = json.dumps(body)
        return FakeResponse(status, text)


class MinjetApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_devices_retries_after_unauthorized(self) -> None:
        session = FakeSession(
            [
                (200, {"code": 200, "token": "token-1"}),
                (401, {"code": 401, "msg": "unauthorized"}),
                (200, {"code": 200, "token": "token-2"}),
                (200, {"code": 200, "data": [{"serialNum": "SN-1", "properties": {}}]}),
            ]
        )
        api = MinjetApi(session=session, username="user", password="pass")

        devices = await api.async_get_devices()

        self.assertEqual(1, len(devices))
        self.assertEqual("SN-1", devices[0]["serialNum"])
        self.assertEqual("token-2", api.token)
        self.assertEqual(["POST", "GET", "POST", "GET"], [call["method"] for call in session.calls])

    async def test_set_rated_power_posts_expected_payload(self) -> None:
        session = FakeSession(
            [
                (200, {"code": 200, "token": "token-1"}),
                (200, {"code": 200, "msg": "success", "data": 123}),
            ]
        )
        api = MinjetApi(session=session, username="user", password="pass")

        result = await api.async_set_rated_power("SN-123", 123)

        self.assertEqual(123, result)
        write_call = session.calls[-1]
        self.assertEqual("POST", write_call["method"])
        self.assertTrue(write_call["url"].endswith("/photovoltaic/setRatedPower/SN-123"))
        self.assertEqual(
            {"key": "ratedPower", "orderCode": "", "value": 123},
            write_call["kwargs"]["json"],
        )

    async def test_set_operation_mode_posts_expected_payload(self) -> None:
        session = FakeSession(
            [
                (200, {"code": 200, "token": "token-1"}),
                (200, {"code": 200, "msg": "success", "data": 1}),
            ]
        )
        api = MinjetApi(session=session, username="user", password="pass")

        result = await api.async_set_operation_mode("SN-123", 1)

        self.assertEqual(1, result)
        write_call = session.calls[-1]
        self.assertTrue(write_call["url"].endswith("/stacking/setProperty/SN-123"))
        self.assertEqual(
            {"key": "batteryPriorityModeStatus", "orderCode": "", "value": 1},
            write_call["kwargs"]["json"],
        )

    async def test_set_battery_discharge_limit_posts_expected_payload(self) -> None:
        session = FakeSession(
            [
                (200, {"code": 200, "token": "token-1"}),
                (200, {"code": 200, "msg": "success", "data": 25}),
            ]
        )
        api = MinjetApi(session=session, username="user", password="pass")

        result = await api.async_set_battery_discharge_limit("SN-123", 25)

        self.assertEqual(25, result)
        write_call = session.calls[-1]
        self.assertTrue(write_call["url"].endswith("/stacking/setProperty/SN-123"))
        self.assertEqual(
            {"key": "batteryDischargeLimit", "orderCode": "", "value": 25},
            write_call["kwargs"]["json"],
        )

    async def test_set_operation_mode_verifies_readback_after_504(self) -> None:
        session = FakeSession(
            [
                (200, {"code": 200, "token": "token-1"}),
                (504, {"code": 504, "msg": "gateway timeout"}),
                (200, {"code": 200, "data": {"batteryPriorityModeStatus": 1}}),
            ]
        )
        api = MinjetApi(session=session, username="user", password="pass")

        with patch.object(api_module.asyncio, "sleep", new=AsyncMock()) as _sleep:
            result = await api.async_set_operation_mode("SN-123", 1)

        self.assertEqual(1, result)
        self.assertEqual(["POST", "POST", "GET"], [call["method"] for call in session.calls])

    async def test_non_json_response_raises_api_error(self) -> None:
        session = FakeSession(
            [
                (200, {"code": 200, "token": "token-1"}),
                (200, "not-json"),
            ]
        )
        api = MinjetApi(session=session, username="user", password="pass")

        with self.assertRaises(MinjetApiError):
            await api.async_get_devices()

    async def test_login_failure_raises_auth_error(self) -> None:
        session = FakeSession([(200, {"code": 500, "msg": "bad credentials"})])
        api = MinjetApi(session=session, username="user", password="pass")

        with self.assertRaises(MinjetAuthError):
            await api.async_login()
