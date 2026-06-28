from __future__ import annotations

import unittest

from tests.support import import_minjet_module

models_module = import_minjet_module("models")
validation_module = import_minjet_module("validation")

build_device_descriptor = models_module.build_device_descriptor
calculate_power_values = models_module.calculate_power_values
resolve_ws_target_serial = models_module.resolve_ws_target_serial
coerce_rated_power = validation_module.coerce_rated_power
coerce_battery_discharge_limit = validation_module.coerce_battery_discharge_limit
coerce_operation_mode = validation_module.coerce_operation_mode


class MinjetModelTests(unittest.TestCase):
    def test_build_device_descriptor_uses_stable_fields(self) -> None:
        descriptor = build_device_descriptor(
            {
                "deviceId": 305,
                "serialNum": "MH7A482403200216",
                "deviceName": "MH7A482403200216",
                "customName": "MH7A-48-Robert",
                "productCode": "MH7A-48",
                "deviceCurrentVersion": "0.03.28",
            }
        )

        self.assertIsNotNone(descriptor)
        assert descriptor is not None
        self.assertEqual("MH7A482403200216", descriptor.serial_num)
        self.assertEqual("305", descriptor.stable_device_id)
        self.assertEqual("MH7A-48-Robert", descriptor.stable_name)

    def test_calculate_power_values_for_discharging(self) -> None:
        values = calculate_power_values(
            {
                "photovoltaicPower": 0,
                "outputPower": 56.5,
                "batteryPower": 56.5,
                "cellVoltMax": 3310,
                "cellVoltMin": 3306,
                "batteryStatus": 2,
            }
        )

        self.assertEqual(56.5, values["battery_discharge_power"])
        self.assertEqual(56.5, values["battery_to_inverter_power"])
        self.assertEqual(0.0, values["pv_to_battery_power"])
        self.assertEqual(4.0, values["cell_voltage_delta"])

    def test_resolve_ws_target_serial_is_ambiguous_for_multiple_devices(self) -> None:
        self.assertIsNone(resolve_ws_target_serial({"properties": {}}, {"SN-1", "SN-2"}))
        self.assertEqual("SN-1", resolve_ws_target_serial({"deviceName": "SN-1"}, {"SN-1", "SN-2"}))
        self.assertEqual("SN-1", resolve_ws_target_serial({"properties": {}}, {"SN-1"}))

    def test_coerce_rated_power_allows_documented_range(self) -> None:
        self.assertEqual(0, coerce_rated_power(0))
        self.assertEqual(800, coerce_rated_power(800))

        with self.assertRaises(ValueError):
            coerce_rated_power(-1)

        with self.assertRaises(ValueError):
            coerce_rated_power(801)

    def test_coerce_battery_discharge_limit_matches_app_constraints(self) -> None:
        self.assertEqual(20, coerce_battery_discharge_limit(20))
        self.assertEqual(25, coerce_battery_discharge_limit(25))
        self.assertEqual(100, coerce_battery_discharge_limit(100))

        with self.assertRaises(ValueError):
            coerce_battery_discharge_limit(15)

        with self.assertRaises(ValueError):
            coerce_battery_discharge_limit(26)

        with self.assertRaises(ValueError):
            coerce_battery_discharge_limit(105)

    def test_coerce_operation_mode_normalizes_supported_values(self) -> None:
        self.assertEqual("erst_entladen", coerce_operation_mode("erst entladen"))
        self.assertEqual("erst_speichern", coerce_operation_mode("erst_speichern"))

        with self.assertRaises(ValueError):
            coerce_operation_mode("charge_first")
