import unittest
import tempfile
from pathlib import Path

from capture_live_validation import (
    _state_copy,
    _plant_preflight,
    _plant_in_cell,
    _safe_sun_items,
    _stable_visible_candidates,
    run_collect_sun_scenario,
    run_current_scenario,
    run_plant_scenario,
    write_evidence_bundle,
)


def sample_state(*, balance=100, items=None, cooldown=True):
    cells = [[None for _ in range(9)] for _ in range(5)]
    return {
        "status": "ok", "valid": True, "decision_ready": False,
        "sample_sequence": 1, "observed_at_utc": "sample",
        "sun_balance": balance,
        "availability": {"plants": "available", "cards": "available",
                         "cards.cost": "available", "cards.cooldown_ready": "available",
                         "cards.usable": "available",
                         "items": "available", "items.position": "available"},
        "cards": [{"slot": 0, "type_code": 0, "cost": 50,
                   "cooldown_ready": cooldown, "usable": cooldown}],
        "board": {"cells": cells}, "items": list(items or []),
    }


class FakeResult:
    def __init__(self, status="success"):
        self.status = status

    def to_dict(self):
        return {"status": self.status}


class FakeExecutor:
    def __init__(self, clock=None, balance_delta=0):
        self.calls = []
        self.clock = clock
        self.balance_delta = balance_delta

    def place_plant(self, *args, **kwargs):
        self.calls.append(("plant", args, kwargs))
        return FakeResult()

    def collect_item(self, item_id, *, timeout_ms, **kwargs):
        self.calls.append(("collect", item_id, timeout_ms, self.clock() if self.clock else None))
        if self.clock:
            self.clock.advance(0.25)
        return FakeResult()


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, amount):
        self.value += amount


class FakeSleeper:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)
        self.clock.advance(seconds)


def sun(item_id, code=4, x=300, y=200, interpretation="i32_pixel_candidate"):
    return {"id": item_id, "type_code": code, "x": x, "y": y,
            "coordinate_interpretation": interpretation}


class LiveValidationLogicTests(unittest.TestCase):
    def test_plant_preflight_rejects_unknown_cooldown_without_action(self):
        accepted, _, _ = _plant_preflight(sample_state(cooldown=False), 1, 0, 0)
        self.assertFalse(accepted)
        state = sample_state(cooldown=False)
        executor = FakeExecutor()
        record, _ = run_plant_scenario(card_slot=1, row=0, col=0, state_reader=lambda: state, executor=executor)
        self.assertEqual(record["status"], "inconclusive")
        self.assertEqual(executor.calls, [])

    def test_plant_preflight_rejects_unrecognized_cell_shape(self):
        state = sample_state()
        state["board"]["cells"][0][0] = {"unexpected": "value"}
        accepted, _, _ = _plant_preflight(state, 1, 0, 0)
        self.assertFalse(accepted)

    def test_plant_confirmation_is_unknown_for_malformed_entity_or_board(self):
        state = sample_state()
        state["board"]["cells"][0][0] = {"plants": [{"type_code": 0}]}
        self.assertIsNone(_plant_in_cell(state, 0, 0, 0))
        state["board"]["cells"] = [[None]]
        self.assertIsNone(_plant_in_cell(state, 0, 0, 0))
        state["board"] = "malformed"
        self.assertIsNone(_plant_in_cell(state, 0, 0, 0))

    def test_plant_preflight_executes_only_once_and_waits_one_second(self):
        state = sample_state()
        calls = []
        executor = FakeExecutor()
        record, _ = run_plant_scenario(card_slot=1, row=0, col=0,
            state_reader=lambda: state, executor=executor, sleeper=calls.append)
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(calls, [1.0])
        self.assertEqual(record["wait_seconds"], 1.0)

    def test_plant_screenshot_failure_keeps_bundle_inconclusive(self):
        state = sample_state()
        def broken_screenshot():
            raise OSError("capture unavailable")
        record, png = run_plant_scenario(card_slot=1, row=0, col=0,
            state_reader=lambda: state, executor=FakeExecutor(), sleeper=lambda _seconds: None,
            screenshot=broken_screenshot)
        self.assertEqual(record["status"], "inconclusive")
        self.assertEqual(record["screenshot_error"], "capture unavailable")
        self.assertIsNone(png)

    def test_sun_filter_accepts_only_safe_types_4_5_6(self):
        state = sample_state(items=[sun(1, 4), sun(2, 5), sun(3, 6), sun(4, 2), sun(5, 4, x=10), sun(6, 4, interpretation="unknown")])
        self.assertEqual([item["id"] for item in _safe_sun_items(state)], [1, 2, 3])

    def test_collect_requires_strictly_more_than_50(self):
        for delta, expected in ((50, "failed"), (51, "success")):
            clock = FakeClock()
            sleeper = FakeSleeper(clock)
            state = sample_state(balance=100, items=[sun(1)])
            count = 0
            def read():
                nonlocal count
                count += 1
                clock.advance(0.05)
                result = dict(state)
                if count > 2:
                    result["items"] = []
                    result["sun_balance"] = 100 + delta
                return result
            executor = FakeExecutor(clock)
            record, _ = run_collect_sun_scenario(state_reader=read, executor=executor, clock=clock, sleeper=sleeper)
            self.assertEqual(record["sun_balance_delta"], delta)
            self.assertEqual(record["status"], expected)
            self.assertLessEqual(record["elapsed_seconds"], 10)
            self.assertEqual(len(executor.calls), 1)
            self.assertTrue(all(call[2] <= 10000 for call in executor.calls))
            self.assertTrue(all(call[2] / 1000 <= 10.05 - call[3] for call in executor.calls))

    def test_collect_polls_until_late_sun_appears_without_busy_spin(self):
        clock = FakeClock()
        sleeper = FakeSleeper(clock)
        count = 0
        state = sample_state(balance=100, items=[])
        def read():
            nonlocal count
            count += 1
            clock.advance(0.01)
            result = dict(state)
            if count == 3:
                result["items"] = [sun(42, 6)]
            elif count >= 4:
                result["items"] = []
                result["sun_balance"] = 151
            return result
        executor = FakeExecutor(clock)
        record, _ = run_collect_sun_scenario(state_reader=read, executor=executor, clock=clock, sleeper=sleeper)
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["attempted_item_ids"], [42])
        self.assertEqual(len(executor.calls), 1)
        self.assertGreater(len(sleeper.calls), 0)
        self.assertTrue(all(0 < pause <= 0.2 for pause in sleeper.calls))

    def test_collect_never_attempts_non_sun_or_unsafe_objects(self):
        clock = FakeClock()
        sleeper = FakeSleeper(clock)
        state = sample_state(items=[sun(1, 3), sun(2, x=850)])
        record, _ = run_collect_sun_scenario(state_reader=lambda: state, executor=FakeExecutor(), clock=clock, sleeper=sleeper)
        self.assertEqual(record["status"], "inconclusive")
        self.assertEqual(record["attempted_item_ids"], [])
        self.assertGreater(len(sleeper.calls), 0)
        self.assertTrue(all(0 < pause <= 0.2 for pause in sleeper.calls))

    def test_collect_deadline_prevents_late_action_and_final_sample(self):
        clock = FakeClock()
        sleeper = FakeSleeper(clock)
        calls = 0
        state = sample_state(items=[sun(1)])
        def read():
            nonlocal calls
            calls += 1
            if calls == 2:
                clock.advance(9.95)
            elif calls == 3:
                clock.advance(0.1)
            return state
        executor = FakeExecutor(clock)
        record, _ = run_collect_sun_scenario(state_reader=read, executor=executor, clock=clock, sleeper=sleeper)
        self.assertEqual(executor.calls, [])
        self.assertIsNone(record["sun_balance_after"])
        self.assertGreater(record["elapsed_seconds"], 10)
        self.assertEqual(record["status"], "inconclusive")
        self.assertEqual(sleeper.calls, [])

    def test_evidence_bundle_writes_png_reference_without_raw_snapshot(self):
        record = {"scenario": "current", "state": {
            "status": "ok", "pid": 123, "profile": "pvz-1051",
            "source": {"module_base": "0xDEADBEEF", "root_address": "0xBAD0", "board_address": "0xCAFE"},
            "raw_snapshot": {"memory": "private"},
        }}
        projection = _state_copy(record["state"])
        self.assertEqual(projection["pid"], 123)
        self.assertEqual(projection["profile"], "pvz-1051")
        for private_field in ("module_base", "root_address", "board_address"):
            self.assertNotIn(private_field, projection["source"])
        with tempfile.TemporaryDirectory() as output:
            path = write_evidence_bundle(Path(output), record, b"PNG")
            contents = path.read_text(encoding="utf-8")
            self.assertNotIn("private", contents)
            self.assertNotIn("0xDEADBEEF", contents)
            self.assertNotIn("0xBAD0", contents)
            self.assertNotIn("0xCAFE", contents)
            for private_field in ("module_base", "root_address", "board_address"):
                self.assertNotIn(private_field, contents)
            self.assertIn('"pid": 123', contents)
            self.assertIn('"profile": "pvz-1051"', contents)
            self.assertIn('"screenshot_file": "pvz-live-', contents)
            self.assertEqual(next(Path(output).glob("*.png")).read_bytes(), b"PNG")

    def test_current_brackets_screenshot_and_ignores_items(self):
        first = sample_state(items=[sun(1)])
        second = sample_state(items=[sun(2)])
        sequence = iter((first, second))
        record, _ = run_current_scenario(state_reader=lambda: next(sequence), screenshot=lambda: (b"png", {"pid": 1}))
        self.assertEqual(record["stable_state_candidates_for_multimodal_review"]["sun_balance"], 100)
        self.assertNotIn("items", record["stable_state_candidates_for_multimodal_review"])
        self.assertIn("items", record["excluded_fields"])

    def test_stable_projection_keeps_only_identical_non_item_fields(self):
        before, after = sample_state(items=[sun(1)]), sample_state(items=[sun(2)])
        before["sun_balance"], after["sun_balance"] = 80, 81
        self.assertNotIn("sun_balance", _stable_visible_candidates(before, after))
        self.assertNotIn("items", _stable_visible_candidates(before, after))


if __name__ == "__main__":
    unittest.main()
