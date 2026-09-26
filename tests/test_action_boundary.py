import unittest

from actions.boundary import ActionBoundary, ActionValidationError
from actions.executor import ActionExecutor, _ActionProblem
from state.projection import project_jev_state


def plant(plant_id, type_name, row, col, *, type_code=1):
    return {
        "id": plant_id,
        "type_code": type_code,
        "type_name": type_name,
        "row": row,
        "col": col,
    }


def all_state(*, plants=None, cards=None, items=None, cells=None, availability=None, sequence=7):
    if cells is None:
        cells = [[None for _ in range(9)] for _ in range(5)]
    return {
        "schema_version": 1,
        "sample_sequence": sequence,
        "availability": {
            "plants": "available",
            "cards": "available",
            "items": "available",
            "items.position": "available",
            **(availability or {}),
        },
        "plants": [] if plants is None else plants,
        "cards": [
            {"slot": 0, "type_code": 1, "type_name": "sunflower"}
        ] if cards is None else cards,
        "items": [] if items is None else items,
        "board": {"rows": 5, "cols": 9, "cells": cells},
        "evidence": {},
    }


def jev_state(*, cards=None, items=None, cells=None, sequence=7):
    if cells is None:
        cells = [[None for _ in range(9)] for _ in range(5)]
    return {
        "sample_sequence": sequence,
        "board": {"rows": 5, "cols": 9, "cells": cells},
        "cards": [
            {
                "slot": 0,
                "type_code": 1,
                "type_name": "sunflower",
                "cost": 50,
                "cooldown_ready": True,
                "usable": True,
            }
        ] if cards is None else cards,
        "items": [] if items is None else items,
    }


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def place_plant(self, card_slot, row, col, **kwargs):
        self.calls.append(("place_plant", card_slot, row, col, kwargs))
        return "place-result"

    def collect_item(self, item_id, **kwargs):
        self.calls.append(("collect_item", item_id, kwargs))
        return "collect-result"

    def shovel_cell(self, row, col, **kwargs):
        self.calls.append(("shovel_cell", row, col, kwargs))
        return "shovel-result"


class ActionExecutorPostconditionTests(unittest.TestCase):
    def test_cell_ids_come_from_all_plants_by_row_and_column_including_layers(self):
        state = all_state(plants=[
            plant(101, "sunflower", 2, 4),
            plant(102, "pumpkin", 2, 4, type_code=30),
            plant(103, "wall_nut", 2, 5, type_code=3),
        ])
        # The nested diagnostic cell representation is deliberately empty; the
        # entity list is the authoritative source for ActionExecutor IDs.
        self.assertEqual(ActionExecutor._cell_ids(state, 2, 4), {101, 102})
        self.assertEqual(ActionExecutor._cell_ids(state, 2, 5), {103})
        self.assertEqual(ActionExecutor._cell_ids(state, 0, 0), set())

    def test_cell_ids_fail_closed_for_unavailable_or_incomplete_entity_data(self):
        valid = all_state(plants=[plant(101, "sunflower", 2, 4)])
        self.assertIsNone(ActionExecutor._cell_ids(
            {**valid, "availability": {**valid["availability"], "plants": "unavailable"}}, 2, 4
        ))
        self.assertIsNone(ActionExecutor._cell_ids(
            {**valid, "plants": [plant(None, "sunflower", 2, 4)]}, 2, 4
        ))
        self.assertIsNone(ActionExecutor._cell_ids(
            {**valid, "plants": [plant(101, "sunflower", 2, 4), plant(101, "pumpkin", 2, 4)]}, 2, 4
        ))
        self.assertIsNone(ActionExecutor._cell_ids(
            {**valid, "plants": [plant(101, "sunflower", 5, 4)]}, 2, 4
        ))
        self.assertIsNone(ActionExecutor._cell_ids(valid, True, 4))

    def test_legacy_low_level_cli_requests_remain_valid_for_all_three_actions(self):
        executor = ActionExecutor()
        requests = (
            {"action": "place_plant", "card_slot": 1, "row": 0, "col": 0},
            {"action": "collect_item", "item_id": 0xFFFFFFFF},
            {"action": "shovel_cell", "row": 4, "col": 8},
        )
        normalized = [executor._validate_request(request) for request in requests]

        self.assertEqual([request["action"] for request in normalized], [
            "place_plant", "collect_item", "shovel_cell",
        ])
        self.assertEqual(normalized[0]["card_slot"], 1)
        self.assertNotIn("expected_type_name", normalized[0])
        self.assertEqual(normalized[1]["item_id"], 0xFFFFFFFF)
        self.assertEqual((normalized[2]["row"], normalized[2]["col"]), (4, 8))

    def _run_place(self, after_state, *, request_type="sunflower", cards=None):
        before = all_state(cards=cards)
        executor = ActionExecutor()
        clicks = []
        executor._send_left_click = lambda *args: clicks.append(args[2])

        def wait_for_postcondition(_context, _request, evaluate):
            outcome, evidence = evaluate(after_state)
            return after_state, outcome, {
                "polls": 1,
                "waited_ms": 0,
                "timeout_ms": 10000,
                "last_observation": evidence,
            }

        executor._wait_for_postcondition = wait_for_postcondition
        result = executor._execute_place(
            {
                "action": "place_plant",
                "card_slot": 1,
                "row": 2,
                "col": 4,
                "expected_type_name": request_type,
                "timeout_ms": 10000,
                "poll_interval_ms": 250,
            },
            None,
            before,
            [],
        )
        return result, clicks

    def test_planting_success_requires_new_entity_type_to_match_selected_card(self):
        after = all_state(plants=[plant(201, "sunflower", 2, 4)])
        result, clicks = self._run_place(after)
        before_summary, after_summary, details, success = result

        self.assertTrue(success)
        self.assertEqual(details["postcondition_result"], "met")
        self.assertEqual(details["expected_type_name"], "sunflower")
        self.assertEqual(details["last_observation"]["observed_type_name"], "sunflower")
        self.assertEqual(details["last_observation"]["new_plant_ids"], [201])
        self.assertEqual(clicks, ["card selection", "lawn cell"])
        self.assertIsNotNone(before_summary)
        self.assertIsNotNone(after_summary)

    def test_planting_wrong_new_type_is_not_confirmed_success(self):
        after = all_state(plants=[plant(202, "wall_nut", 2, 4, type_code=3)])
        result, _clicks = self._run_place(after)
        _before, _after, details, success = result

        self.assertFalse(success)
        self.assertEqual(details["postcondition_result"], "mismatch")
        self.assertEqual(details["last_observation"]["expected_type_name"], "sunflower")
        self.assertEqual(details["last_observation"]["observed_type_name"], "wall_nut")

    def test_shovel_confirms_cell_level_removal_when_any_one_layer_id_disappears(self):
        before = all_state(plants=[
            plant(301, "sunflower", 2, 4),
            plant(302, "pumpkin", 2, 4, type_code=30),
        ])
        after = all_state(plants=[plant(302, "pumpkin", 2, 4, type_code=30)])
        executor = ActionExecutor()
        clicks = []
        executor._send_left_click = lambda *args: clicks.append(args[2])

        def wait_for_postcondition(_context, _request, evaluate):
            outcome, evidence = evaluate(after)
            return after, outcome, {
                "polls": 1,
                "waited_ms": 0,
                "timeout_ms": 10000,
                "last_observation": evidence,
            }

        executor._wait_for_postcondition = wait_for_postcondition
        _before, _after, details, success = executor._execute_shovel(
            {"action": "shovel_cell", "row": 2, "col": 4, "timeout_ms": 10000,
             "poll_interval_ms": 250},
            None,
            before,
            [],
        )

        self.assertTrue(success)
        self.assertEqual(details["last_observation"]["removed_plant_ids"], [301])
        self.assertEqual(details["native_shovel_clicks_per_request"], 1)
        self.assertEqual(clicks, ["native shovel selection", "lawn cell"])

    def test_place_refuses_unresolved_or_mismatched_card_type_before_input(self):
        executor = ActionExecutor()
        clicks = []
        executor._send_left_click = lambda *args: clicks.append(args[2])
        before = all_state()
        request = {
            "action": "place_plant", "card_slot": 1, "row": 2, "col": 4,
            "expected_type_name": "peashooter",
        }
        with self.assertRaisesRegex(_ActionProblem, "matches"):
            executor._execute_place(request, None, before, [])
        self.assertEqual(clicks, [])

        duplicate_cards = [
            {"slot": 0, "type_code": 1, "type_name": "sunflower"},
            {"slot": 0, "type_code": 3, "type_name": "wall_nut"},
        ]
        with self.assertRaisesRegex(_ActionProblem, "unavailable or ambiguous"):
            executor._execute_place(
                {**request, "expected_type_name": "sunflower"},
                None,
                all_state(cards=duplicate_cards),
                [],
            )
        self.assertEqual(clicks, [])


class ActionBoundaryTests(unittest.TestCase):
    def test_place_maps_unique_jev_card_slots_zero_and_nine_to_executor_one_and_ten(self):
        for state_slot in (0, 9):
            with self.subTest(state_slot=state_slot):
                card = {
                    "slot": state_slot,
                    "type_code": 1,
                    "type_name": "sunflower",
                    "cost": 50,
                    "cooldown_ready": True,
                    "usable": True,
                }
                jev = jev_state(cards=[card])
                sample = all_state(cards=[{
                    "slot": state_slot,
                    "type_code": 1,
                    "type_name": "sunflower",
                }])
                fake = FakeExecutor()

                result = ActionBoundary(fake).dispatch(
                    {"action": "place_plant", "type_name": "sunflower", "row": 2, "col": 4},
                    jev_state=jev,
                    all_state=sample,
                )

                self.assertEqual(result, "place-result")
                self.assertEqual(fake.calls, [(
                    "place_plant", state_slot + 1, 2, 4,
                    {"expected_type_name": "sunflower"},
                )])

    def test_place_requires_strict_true_usable_and_null_target_cell(self):
        request = {"action": "place_plant", "type_name": "sunflower", "row": 1, "col": 2}
        for usable in (False, None, 1, "true"):
            with self.subTest(usable=usable):
                card = dict(jev_state()["cards"][0], usable=usable)
                fake = FakeExecutor()
                with self.assertRaisesRegex(ActionValidationError, "boolean true"):
                    ActionBoundary(fake).dispatch(
                        request,
                        jev_state=jev_state(cards=[card]),
                        all_state=all_state(),
                    )
                self.assertEqual(fake.calls, [])

        for cell in (False, "plant:sunflower"):
            with self.subTest(cell=cell):
                cells = [[None for _ in range(9)] for _ in range(5)]
                cells[1][2] = cell
                fake = FakeExecutor()
                with self.assertRaisesRegex(ActionValidationError, "to be null"):
                    ActionBoundary(fake).dispatch(
                        request,
                        jev_state=jev_state(cells=cells),
                        all_state=all_state(),
                    )
                self.assertEqual(fake.calls, [])

    def test_place_rejects_duplicate_card_name_conflicting_all_state_cell_and_bad_grid(self):
        request = {"action": "place_plant", "type_name": "sunflower", "row": 1, "col": 2}
        duplicate_cards = [
            dict(jev_state()["cards"][0], slot=0),
            dict(jev_state()["cards"][0], slot=1),
        ]
        fake = FakeExecutor()
        with self.assertRaisesRegex(ActionValidationError, "exactly one"):
            ActionBoundary(fake).dispatch(
                request,
                jev_state=jev_state(cards=duplicate_cards),
                all_state=all_state(),
            )
        self.assertEqual(fake.calls, [])

        fake = FakeExecutor()
        with self.assertRaisesRegex(ActionValidationError, "disagree"):
            ActionBoundary(fake).dispatch(
                request,
                jev_state=jev_state(),
                all_state=all_state(plants=[plant(101, "sunflower", 1, 2)]),
            )
        self.assertEqual(fake.calls, [])

        fake = FakeExecutor()
        with self.assertRaisesRegex(ActionValidationError, "malformed"):
            ActionBoundary(fake).dispatch(
                request,
                jev_state=jev_state(cells=[[None] * 9]),
                all_state=all_state(),
            )
        self.assertEqual(fake.calls, [])

    def test_shovel_is_a_cell_level_action_and_requires_matching_plant_evidence(self):
        plants = [
            plant(101, "sunflower", 1, 2),
            plant(102, "pumpkin", 1, 2, type_code=30),
        ]
        cells = [[None for _ in range(9)] for _ in range(5)]
        cells[1][2] = "plant:sunflower"
        fake = FakeExecutor()
        result = ActionBoundary(fake).dispatch(
            {"action": "shovel_cell", "row": 1, "col": 2},
            jev_state=jev_state(cells=cells),
            all_state=all_state(plants=plants),
        )
        self.assertEqual(result, "shovel-result")
        self.assertEqual(fake.calls, [("shovel_cell", 1, 2, {})])

        for cell in (None, False, "plant:unknown"):
            with self.subTest(cell=cell):
                cells[1][2] = cell
                fake = FakeExecutor()
                with self.assertRaises(ActionValidationError):
                    ActionBoundary(fake).dispatch(
                        {"action": "shovel_cell", "row": 1, "col": 2},
                        jev_state=jev_state(cells=cells),
                        all_state=all_state(plants=plants),
                    )
                self.assertEqual(fake.calls, [])

        cells[1][2] = "plant:sunflower"
        fake = FakeExecutor()
        with self.assertRaisesRegex(ActionValidationError, "disagree"):
            ActionBoundary(fake).dispatch(
                {"action": "shovel_cell", "row": 1, "col": 2},
                jev_state=jev_state(cells=cells),
                all_state=all_state(plants=[plant(103, "wall_nut", 1, 2, type_code=3)]),
            )
        self.assertEqual(fake.calls, [])

    def test_collect_resolves_visible_attributes_to_one_same_sample_all_state_id(self):
        item = {"type_code": 4, "type_name": "sun", "x": 310.0, "y": 212.0}
        all_item = {"id": 0x12345678, **item}
        jev = jev_state(items=[item])
        sample = all_state(items=[all_item])
        fake = FakeExecutor()

        result = ActionBoundary(fake).dispatch(
            {"action": "collect_item", **item},
            jev_state=jev,
            all_state=sample,
        )

        self.assertEqual(result, "collect-result")
        self.assertEqual(fake.calls, [("collect_item", all_item["id"], {})])
        self.assertNotIn("id", jev["items"][0])

    def test_collect_rejects_zero_or_multiple_visible_matches_bad_evidence_and_sample_mismatch(self):
        item = {"type_code": 4, "type_name": "sun", "x": 310.0, "y": 212.0}
        request = {"action": "collect_item", **item}
        fake = FakeExecutor()
        with self.assertRaisesRegex(ActionValidationError, "exactly one current All State item ID"):
            ActionBoundary(fake).dispatch(
                request,
                jev_state=jev_state(items=[item]),
                all_state=all_state(items=[{"id": 10, **{**item, "x": 999.0}}]),
            )
        self.assertEqual(fake.calls, [])

        duplicate = {"id": 11, **item}
        fake = FakeExecutor()
        with self.assertRaisesRegex(ActionValidationError, "exactly one"):
            ActionBoundary(fake).dispatch(
                request,
                jev_state=jev_state(items=[item]),
                all_state=all_state(items=[{"id": 10, **item}, duplicate]),
            )
        self.assertEqual(fake.calls, [])

        fake = FakeExecutor()
        with self.assertRaisesRegex(ActionValidationError, "exactly once"):
            ActionBoundary(fake).dispatch(
                request,
                jev_state=jev_state(items=[item, dict(item)]),
                all_state=all_state(items=[{"id": 10, **item}]),
            )
        self.assertEqual(fake.calls, [])

        fake = FakeExecutor()
        with self.assertRaisesRegex(ActionValidationError, "same valid sample_sequence"):
            ActionBoundary(fake).dispatch(
                request,
                jev_state=jev_state(items=[item]),
                all_state=all_state(items=[{"id": 10, **item}], sequence=8),
            )
        self.assertEqual(fake.calls, [])

        fake = FakeExecutor()
        with self.assertRaisesRegex(ActionValidationError, "unavailable"):
            ActionBoundary(fake).dispatch(
                request,
                jev_state=jev_state(items=[item]),
                all_state=all_state(
                    items=[{"id": 10, **item}],
                    availability={"items.position": "unavailable"},
                ),
            )
        self.assertEqual(fake.calls, [])

    def test_action_boundary_rejects_unknown_actions_extra_fields_and_invalid_coordinates(self):
        fake = FakeExecutor()
        boundary = ActionBoundary(fake)
        valid_states = {"jev_state": jev_state(), "all_state": all_state()}
        for request in (
            {"action": "wait"},
            {"action": "shovel_cell", "row": 1, "col": True},
            {"action": "shovel_cell", "row": 1, "col": 2, "plant_id": 101},
            {"action": "shovel_cell", "row": 1, "col": 2, "timeout_ms": 99},
        ):
            with self.subTest(request=request):
                with self.assertRaises(ActionValidationError):
                    boundary.dispatch(request, **valid_states)
        self.assertEqual(fake.calls, [])

    def test_collect_rejects_unknown_or_incomplete_visible_item_attributes(self):
        item = {"type_code": 4, "type_name": "sun", "x": 310.0, "y": 212.0}
        request = {"action": "collect_item", **item}
        invalid_requests = (
            {**request, "type_name": "unknown"},
            {**request, "type_name": None},
            {**request, "type_code": True},
            {**request, "x": float("nan")},
            {key: value for key, value in request.items() if key != "y"},
        )
        for invalid in invalid_requests:
            with self.subTest(request=invalid):
                fake = FakeExecutor()
                with self.assertRaises(ActionValidationError):
                    ActionBoundary(fake).dispatch(
                        invalid,
                        jev_state=jev_state(items=[item]),
                        all_state=all_state(items=[{"id": 10, **item}]),
                    )
                self.assertEqual(fake.calls, [])

    def test_jev_projection_still_omits_item_ids_and_diagnostics(self):
        item = {"id": 88, "type_code": 4, "type_name": "sun", "x": 100.0, "y": 200.0}
        sample = all_state(items=[item])

        projected = project_jev_state(sample)

        self.assertEqual(projected["items"], [{
            "type_code": 4, "type_name": "sun", "x": 100.0, "y": 200.0,
        }])
        self.assertNotIn("availability", projected)
        self.assertNotIn("source", projected)
        self.assertNotIn("raw_snapshot", projected)


if __name__ == "__main__":
    unittest.main()
