from __future__ import annotations

import unittest

from tests.support import import_minjet_module

zero_export_module = import_minjet_module("zero_export")

compute_next_target = zero_export_module.compute_next_target
evaluate_zero_export_cycle = zero_export_module.evaluate_zero_export_cycle
resolve_last_setpoint = zero_export_module.resolve_last_setpoint


class MinjetZeroExportTests(unittest.TestCase):
    def test_grid_import_increases_target(self) -> None:
        next_target, should_write, reason = compute_next_target(
            old_target=100,
            grid_power=200,
            deadband=30,
            step_limit=400,
            min_power=0,
            max_power=800,
            min_write_delta=30,
        )

        self.assertEqual(300, next_target)
        self.assertTrue(should_write)
        self.assertIsNone(reason)

    def test_grid_export_decreases_target(self) -> None:
        next_target, should_write, reason = compute_next_target(
            old_target=300,
            grid_power=-150,
            deadband=30,
            step_limit=400,
            min_power=0,
            max_power=800,
            min_write_delta=30,
        )

        self.assertEqual(150, next_target)
        self.assertTrue(should_write)
        self.assertIsNone(reason)

    def test_deadband_blocks_write(self) -> None:
        next_target, should_write, reason = compute_next_target(
            old_target=240,
            grid_power=20,
            deadband=30,
            step_limit=100,
            min_power=0,
            max_power=800,
            min_write_delta=30,
        )

        self.assertEqual(240, next_target)
        self.assertFalse(should_write)
        self.assertEqual("within_deadband", reason)

    def test_step_limit_caps_correction(self) -> None:
        next_target, should_write, reason = compute_next_target(
            old_target=100,
            grid_power=260,
            deadband=30,
            step_limit=100,
            min_power=0,
            max_power=800,
            min_write_delta=30,
        )

        self.assertEqual(200, next_target)
        self.assertTrue(should_write)
        self.assertIsNone(reason)

    def test_clamp_prevents_out_of_range_targets(self) -> None:
        high_target, should_write_high, _reason_high = compute_next_target(
            old_target=760,
            grid_power=200,
            deadband=0,
            step_limit=400,
            min_power=0,
            max_power=800,
            min_write_delta=30,
        )
        low_target, should_write_low, _reason_low = compute_next_target(
            old_target=40,
            grid_power=-200,
            deadband=0,
            step_limit=400,
            min_power=0,
            max_power=800,
            min_write_delta=30,
        )

        self.assertEqual(800, high_target)
        self.assertTrue(should_write_high)
        self.assertEqual(0, low_target)
        self.assertTrue(should_write_low)

    def test_min_write_delta_blocks_small_changes(self) -> None:
        next_target, should_write, reason = compute_next_target(
            old_target=100,
            grid_power=40,
            deadband=0,
            step_limit=100,
            min_power=0,
            max_power=800,
            min_write_delta=50,
        )

        self.assertEqual(140, next_target)
        self.assertFalse(should_write)
        self.assertEqual("delta_too_small", reason)

    def test_unavailable_grid_sensor_blocks_cycle(self) -> None:
        decision = evaluate_zero_export_cycle(
            enabled=True,
            device_offline=False,
            raw_grid_power="unavailable",
            grid_sign=1,
            old_target=120,
            deadband=30,
            step_limit=100,
            min_power=0,
            max_power=800,
            min_write_delta=30,
        )

        self.assertFalse(decision.active)
        self.assertEqual("grid_unavailable", decision.block_reason)
        self.assertFalse(decision.should_write)
        self.assertEqual(120, decision.next_target)

    def test_offline_blocks_cycle(self) -> None:
        decision = evaluate_zero_export_cycle(
            enabled=True,
            device_offline=True,
            raw_grid_power="50",
            grid_sign=1,
            old_target=120,
            deadband=30,
            step_limit=100,
            min_power=0,
            max_power=800,
            min_write_delta=30,
        )

        self.assertFalse(decision.active)
        self.assertEqual("device_offline", decision.block_reason)
        self.assertFalse(decision.should_write)

    def test_last_setpoint_helper_is_used_as_start_value(self) -> None:
        self.assertEqual(345, resolve_last_setpoint("345", 0, 800))
        self.assertEqual(0, resolve_last_setpoint("unknown", 0, 800))

    def test_recent_average_uses_last_two_values(self) -> None:
        decision = evaluate_zero_export_cycle(
            enabled=True,
            device_offline=False,
            raw_grid_power="120",
            grid_sign=1,
            old_target=200,
            deadband=30,
            step_limit=500,
            min_power=0,
            max_power=800,
            min_write_delta=30,
            recent_grid_powers=[80.0, 120.0],
        )

        self.assertTrue(decision.active)
        self.assertEqual(100.0, decision.averaged_grid_power)
        self.assertEqual(300, decision.next_target)
        self.assertTrue(decision.should_write)

