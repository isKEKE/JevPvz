import unittest
import json
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from state.builder import build_state, capture_state
from state.schema import to_json_record
from state.projection import project_jev_state
from runtime.process import TargetNotRunningError


def domain(entities):
    return {
        "status": "provisional",
        "evidence_level": "observed_once",
        "reported_live_count": len(entities),
        "scanned_live_count": len(entities),
        "counts_match": True,
        "entities": entities,
    }


def sample(*, plants=None, zombies=None, items=None):
    plants = [] if plants is None else plants
    zombies = [] if zombies is None else zombies
    items = [] if items is None else items
    return {
        "captured_at_utc": "2026-09-24T02:00:00.000Z",
        "module_base": "0x00400000",
        "root_address": "0x01000000",
        "board_address": "0x02000000",
        "sun": {"value": 3333, "evidence_level": "observed_once"},
        "arrays": {"plants": domain(plants), "zombies": domain(zombies), "items": domain(items)},
        "candidates": {
            "seed_bank": {
                "status": "provisional",
                "evidence_level": "observed_once",
                "slot_count": {"value": 2},
                "slots": [
                    {"index": 0, "fields": {"slot_type": {"value": 35}, "imitator_type": {"value": 0}, "cooldown_progress": {"value": 0}, "cooldown_total": {"value": 300}, "usable_flag": {"value": 1}}},
                    {"index": 1, "fields": {"slot_type": {"value": 5}, "imitator_type": {"value": 0}, "cooldown_progress": {"value": 10}, "cooldown_total": {"value": 300}, "usable_flag": {"value": 0}}},
                ],
            },
            "game_progress": {
                "raw_candidate_fields": {
                    "mode": {"value": 0},
                    "pause_flag": {"value": 1},
                }
            },
            "terrain": {"status": "candidate", "raw_hex": "00" * 54},
            "plant_definition_costs": {"status": "provisional", "entries": {
                "35": {"type_code": 35, "cost": 75},
                "5": {"type_code": 5, "cost": 175},
            }},
        },
    }


class StateBuilderTests(unittest.TestCase):

    def test_snapshot_cli_selects_jev_and_keeps_all_as_default(self):
        from main import build_parser, run_snapshot

        self.assertEqual(build_parser().parse_args(["snapshot", "--once"]).profile, "all")
        sample_record = to_json_record(build_state(sample()))
        for profile, expected in (("all", sample_record), ("jev", project_jev_state(sample_record))):
            stdout = StringIO()
            with patch("main.capture_state", return_value=sample_record), redirect_stdout(stdout):
                self.assertEqual(run_snapshot(once=True, interval_ms=200, profile=profile), 0)
            self.assertEqual(json.loads(stdout.getvalue()), expected)

    def test_jev_projection_is_an_explicit_compact_allowlist_and_preserves_unknowns(self):
        all_state = to_json_record(build_state(sample(
            plants=[{"type": 1, "row": 1, "column": 2}],
            zombies=[{"type": 4, "row": 1, "x": 600.0, "y": 250.0, "hp": 270, "helmet_hp": 1100}],
            items=[{"type": 4, "x": 321.0, "y": 222.0}],
        )))
        all_state["game"]["background"] = "day"
        all_state["board"]["plantability"][0][0] = False
        all_state["future_diagnostic"] = {"secret": "must not leak"}
        jev = project_jev_state(all_state)

        self.assertEqual(jev["sample_sequence"], all_state["sample_sequence"])
        self.assertEqual(jev["observed_at_utc"], all_state["observed_at_utc"])
        self.assertEqual(jev["board"]["cells"][1][2], "plant:sunflower")
        self.assertIsNone(jev["board"]["cells"][0][1])
        self.assertIs(jev["board"]["cells"][0][0], False)
        self.assertEqual(set(jev["board"]), {"rows", "cols", "cells"})
        self.assertIn("terrain", all_state["board"])
        self.assertIn("plantability", all_state["board"])
        self.assertEqual(jev["plants"], [{"type_code": 1, "type_name": "sunflower", "row": 1, "col": 2}])
        self.assertEqual(jev["zombies"][0]["hp"], jev["zombies"][0]["body_hp"])
        self.assertEqual(jev["zombies"][0]["distance_to_house_px"], all_state["zombies"][0]["distance_to_house_px"])
        self.assertEqual(jev["zombies"][0]["distance_to_house_cells"], all_state["zombies"][0]["distance_to_house_cells"])
        self.assertNotIn("nearest_zombie_distance_to_house_px", jev["zombies"][0])
        self.assertNotIn("nearest_zombie_distance_to_house_cells", jev["zombies"][0])
        self.assertEqual([card["cooldown_ready"] for card in jev["cards"]], [True, False])
        self.assertEqual([card["usable"] for card in jev["cards"]], [False, False])
        self.assertNotIn("availability", jev)
        self.assertIn("availability", all_state)
        self.assertEqual(all_state["availability"]["cards.cooldown_ready"], "available")
        self.assertEqual(jev["items"][0], {"type_code": 4, "type_name": "sun", "x": 321.0, "y": 222.0})
        self.assertNotIn("collectible_suns", jev)
        self.assertIn("collectible_suns", all_state)
        self.assertIn("nearest_zombie_distance_to_house_px", all_state["lanes"][1])
        self.assertIn("nearest_zombie_distance_to_house_cells", all_state["lanes"][1])
        self.assertEqual(jev["lanes"][1]["row"], 1)
        self.assertEqual(jev["lanes"][1]["zombie_count"], 1)
        for lane in jev["lanes"]:
            self.assertNotIn("nearest_zombie_distance_to_house_px", lane)
            self.assertIn("nearest_zombie_distance_to_house_cells", lane)
        self.assertNotIn("source", jev)
        self.assertNotIn("raw_snapshot", jev)
        self.assertNotIn("evidence", jev)
        self.assertNotIn("errors", jev)
        self.assertNotIn("future_diagnostic", jev)
        self.assertNotIn("id", jev["zombies"][0])
        self.assertNotIn("total_hp", jev["zombies"][0])

    def test_jev_projection_keeps_all_state_input_unchanged(self):
        import copy
        all_state = to_json_record(build_state(sample()))
        before = copy.deepcopy(all_state)
        project_jev_state(all_state)
        self.assertEqual(all_state, before)

    def test_jev_board_occupancy_stays_null_when_unobserved_and_keeps_observed_empty_grid(self):
        import copy
        all_state = to_json_record(build_state(sample()))
        all_state["game"]["background"] = "day"

        absent = copy.deepcopy(all_state)
        absent["board"].pop("cells")
        absent["availability"].pop("board.occupancy")
        absent_jev = project_jev_state(absent)
        self.assertIsNone(absent_jev["board"]["cells"])
        self.assertNotIn("availability", absent_jev)

        invalid = copy.deepcopy(all_state)
        invalid["board"]["cells"] = [[None] * 9]
        invalid["availability"]["board.occupancy"] = "error"
        invalid_jev = project_jev_state(invalid)
        self.assertIsNone(invalid_jev["board"]["cells"])
        self.assertNotIn("availability", invalid_jev)

        empty = copy.deepcopy(all_state)
        empty["board"]["cells"] = [[None] * 9 for _ in range(5)]
        empty["availability"]["board.occupancy"] = "provisional"
        empty_jev = project_jev_state(empty)
        self.assertEqual(empty_jev["board"]["cells"], [[None] * 9 for _ in range(5)])
        self.assertEqual(set(empty_jev["board"]), {"rows", "cols", "cells"})
        self.assertNotIn("availability", empty_jev)

        nonplantable = copy.deepcopy(empty)
        nonplantable["board"]["plantability"][2][4] = False
        nonplantable_jev = project_jev_state(nonplantable)
        self.assertIs(nonplantable_jev["board"]["cells"][2][4], False)

        unsupported = copy.deepcopy(empty)
        unsupported["game"]["background"] = "pool"
        unsupported_jev = project_jev_state(unsupported)
        self.assertIsNone(unsupported_jev["board"]["cells"])

    def test_card_cost_uses_adventure_base_and_endless_upgrade_plant_count(self):
        raw = sample(plants=[
            {"slot": 0, "object_id": 101, "type": 40, "row": 0, "column": 0},
            {"slot": 1, "object_id": 102, "type": 40, "row": 1, "column": 0},
            {"slot": 2, "object_id": 103, "type": 0, "row": 2, "column": 0},
        ])
        raw["candidates"]["seed_bank"]["slots"] = [
            {"index": 0, "fields": {"slot_type": {"value": 40}, "imitator_type": {"value": 0}}},
            {"index": 1, "fields": {"slot_type": {"value": 0}, "imitator_type": {"value": 0}}},
        ]
        raw["candidates"]["seed_bank"]["slot_count"] = {"value": 2}
        raw["candidates"]["plant_definition_costs"]["entries"].update({
            "40": {"type_code": 40, "cost": 250},
            "0": {"type_code": 0, "cost": 100},
        })
        raw["candidates"]["game_progress"]["raw_candidate_fields"]["mode"] = {"value": 11}

        endless = to_json_record(build_state(raw))

        self.assertEqual([card["cost"] for card in endless["cards"]], [350, 100])
        self.assertEqual(endless["availability"]["cards.cost"], "provisional")
        self.assertIn("Endless price event not confirmed", endless["evidence"]["cards.cost"])
        self.assertFalse(any(key.startswith("affordable") for card in endless["cards"] for key in card))
        self.assertIsNone(endless["cards"][0]["cooldown_ready"])
        self.assertEqual(endless["availability"]["cards.cooldown_ready"], "unavailable")

        raw["candidates"]["game_progress"]["raw_candidate_fields"]["mode"] = {"value": 6}
        hard_survival = to_json_record(build_state(raw))
        self.assertEqual(hard_survival["cards"][0]["cost"], 250)
        self.assertEqual(hard_survival["availability"]["cards.cost"], "available")

        raw["candidates"]["game_progress"]["raw_candidate_fields"]["mode"] = {"value": 0}
        adventure = to_json_record(build_state(raw))
        self.assertEqual(adventure["cards"][0]["cost"], 250)

    def test_initial_ready_and_cooling_cards_get_boolean_readiness_at_counter_boundaries(self):
        raw = sample()
        progress = raw["candidates"]["game_progress"]["raw_candidate_fields"]
        progress.update({
            "scene": {"value": 3},
            "pause_flag": {"value": 0},
            "won_flag": {"value": 0},
        })
        raw["candidates"]["seed_bank"]["slots"] = [
            {"index": 0, "fields": {"slot_type": {"value": 35}, "imitator_type": {"value": 0}, "cooldown_progress": {"value": 300}, "cooldown_total": {"value": 300}, "usable_flag": {"value": 1}}},
            {"index": 1, "fields": {"slot_type": {"value": 5}, "imitator_type": {"value": 0}, "cooldown_progress": {"value": 300}, "cooldown_total": {"value": 300}, "usable_flag": {"value": 0}}},
        ]

        record = to_json_record(build_state(raw))

        self.assertEqual([card["cooldown_ready"] for card in record["cards"]], [True, False])
        self.assertEqual([card["usable"] for card in record["cards"]], [True, False])
        self.assertEqual(record["availability"]["cards.cooldown_ready"], "available")
        self.assertEqual(record["availability"]["cards.usable"], "available")

    def test_builds_5_by_9_occupancy_and_lane_counts_from_observed_entities(self):
        raw = sample(
            plants=[
                {"slot": 0, "object_id": 100, "type": 1, "row": 0, "column": 3},
                {"slot": 1, "object_id": 101, "type": 29, "row": 2, "column": 3},
            ],
            zombies=[
                {"slot": 9, "object_id": 200, "type": 0, "row": 2, "x": 687.0, "y": 250.0, "hp": 270},
                {"slot": 8, "object_id": 201, "type": 2, "row": 2, "x": 700.5, "y": 251.0, "hp": 120},
            ],
            items=[{"slot": 0, "object_id": 300, "type": 4, "x": 551.0, "y": 448.0, "coordinate_interpretation": "f32_pixel_candidate"}],
        )

        record = to_json_record(build_state(raw, source={"pid": 26120, "exe_sha256": "ABC"}))

        self.assertEqual((record["board"]["rows"], record["board"]["cols"]), (5, 9))
        self.assertEqual(record["board"]["cells"][0][3]["type_code"], 1)
        self.assertEqual(record["board"]["cells"][2][3]["type_code"], 29)
        self.assertEqual(record["board"]["cells"][0][0], None)
        self.assertEqual(record["availability"]["plants"], "provisional")
        self.assertEqual([lane["zombie_count"] for lane in record["lanes"]], [0, 0, 2, 0, 0])
        self.assertTrue(all(zombie["distance_to_house_px"] is None for zombie in record["zombies"]))
        self.assertTrue(all(zombie["distance_to_house_cells"] is None for zombie in record["zombies"]))
        self.assertTrue(all("progress_to_house" not in zombie for zombie in record["zombies"]))
        self.assertEqual(record["availability"]["zombies.distance_to_house_px"], "unavailable")
        self.assertEqual(record["availability"]["zombies.distance_to_house_cells"], "unavailable")
        self.assertIsNone(record["lanes"][2]["nearest_zombie_distance_to_house_px"])
        self.assertIsNone(record["lanes"][2]["nearest_zombie_distance_to_house_cells"])
        self.assertEqual((record["zombies"][0]["x"], record["zombies"][0]["y"], record["zombies"][0]["hp"]), (687.0, 250.0, 270))
        self.assertEqual(record["items"][0]["type_name"], "sun")
        self.assertEqual(record["items"][0]["type_meaning"], "candidate")
        self.assertIsNone(record["collectible_suns"])
        self.assertEqual(record["availability"]["cards.cost"], "available")
        self.assertEqual(record["cards"][0]["type_name"], "coffee_bean")
        self.assertEqual(record["cards"][0]["cost"], 75)
        self.assertEqual(record["cards"][0]["cost_source"], "plant_definition_table_verified_with_gameplay")
        self.assertEqual(record["cards"][1]["type_name"], "snow_pea")
        self.assertEqual(record["cards"][1]["cost"], 175)
        self.assertEqual(record["board"]["cells"][0][3]["type_name"], "sunflower")
        self.assertEqual(record["zombies"][0]["type_name"], "normal_zombie")
        self.assertEqual(record["zombies"][1]["type_name"], "conehead_zombie")
        self.assertEqual(record["cards"][0]["cooldown_ready"], True)
        self.assertEqual(record["cards"][1]["cooldown_ready"], False)
        self.assertEqual(record["availability"]["cards.cooldown_ready"], "available")
        self.assertFalse(record["decision_ready"])

    def test_pumpkin_and_tall_nut_share_one_cell_without_erasing_the_lawn(self):
        for plant_order in (
            [(30, 0), (23, 1)],
            [(23, 0), (30, 1)],
        ):
            raw = sample(plants=[
                {"slot": slot, "object_id": 100 + slot, "type": type_code, "row": 0, "column": 6}
                for type_code, slot in plant_order
            ])

            record = to_json_record(build_state(raw))

            self.assertTrue(record["valid"])
            self.assertEqual(record["availability"]["plants"], "provisional")
            self.assertEqual(len(record["plants"]), 2)
            self.assertEqual(record["board"]["cells"][0][6]["type_name"], "tall_nut")
            self.assertEqual(record["board"]["cells"][0][6]["plant_count"], 2)
            self.assertEqual(
                [plant["type_name"] for plant in record["board"]["cells"][0][6]["plants"]],
                ["tall_nut", "pumpkin"],
            )
            self.assertIsNone(record["board"]["cells"][0][0])

    def test_carrier_and_three_layer_cells_keep_all_entities_with_stable_main_plant(self):
        entities = [
            {"slot": 8, "object_id": 108, "type": 30, "row": 2, "column": 4},
            {"slot": 3, "object_id": 103, "type": 16, "row": 2, "column": 4},
            {"slot": 5, "object_id": 105, "type": 1, "row": 2, "column": 4},
            {"slot": 2, "object_id": 102, "type": 33, "row": 1, "column": 2},
            {"slot": 4, "object_id": 104, "type": 32, "row": 1, "column": 2},
            {"slot": 9, "object_id": 109, "type": 23, "row": 0, "column": 0},
        ]
        for ordered_entities in (entities, list(reversed(entities))):
            with self.subTest(first_type=ordered_entities[0]["type"]):
                record = to_json_record(build_state(sample(plants=ordered_entities)))
                cells = record["board"]["cells"]
                self.assertTrue(record["valid"])
                self.assertEqual(len(record["plants"]), 6)
                self.assertEqual(sum(len(cell["plants"]) for row in cells for cell in row if cell), 6)
                self.assertEqual(sum(cell is not None for row in cells for cell in row), 3)
                self.assertEqual([plant["type_code"] for plant in cells[2][4]["plants"]], [1, 30, 16])
                self.assertEqual(cells[2][4]["type_name"], "sunflower")
                self.assertEqual([plant["id"] for plant in cells[2][4]["plants"]], [105, 108, 103])
                self.assertEqual([plant["type_code"] for plant in cells[1][2]["plants"]], [32, 33])
                self.assertEqual(cells[0][0]["plant_count"], 1)

    def test_same_layer_main_plant_is_independent_of_array_and_slot_order(self):
        for first_slot, second_slot in ((0, 1), (1, 0)):
            entities = [
                {"slot": first_slot, "object_id": 200, "type": 29, "row": 0, "column": 0},
                {"slot": second_slot, "object_id": 201, "type": 23, "row": 0, "column": 0},
            ]
            for ordering in (entities, list(reversed(entities))):
                cell = to_json_record(build_state(sample(plants=ordering)))["board"]["cells"][0][0]
                self.assertEqual(cell["type_code"], 23)
                self.assertEqual([plant["type_code"] for plant in cell["plants"]], [23, 29])

    def test_armored_zombie_exposes_body_armor_and_total_hp(self):
        raw = sample(zombies=[{
            "type": 4, "row": 2, "x": 680.0, "y": 250.0,
            "hp": 270, "helmet_hp": 1100, "shield_hp": 0, "balloon_hp": 0,
        }])

        zombie = to_json_record(build_state(raw))["zombies"][0]

        self.assertEqual(zombie["body_hp"], 270)
        self.assertEqual(zombie["hp"], 270)
        self.assertEqual(zombie["helmet_hp"], 1100)
        self.assertEqual(zombie["total_hp"], 1370)

    def test_cone_bucket_shield_and_unarmored_parts_remain_separate(self):
        raw = sample(zombies=[
            {"type": 2, "row": 0, "x": 680.0, "y": 150.0,
             "hp": 270, "helmet_hp": 370, "shield_hp": 0, "balloon_hp": 0},
            {"type": 4, "row": 1, "x": 680.0, "y": 200.0,
             "hp": 270, "helmet_hp": 1100, "shield_hp": 0, "balloon_hp": 0},
            {"type": 6, "row": 2, "x": 680.0, "y": 250.0,
             "hp": 270, "helmet_hp": 0, "shield_hp": 1100, "balloon_hp": 0},
            {"type": 0, "row": 3, "x": 680.0, "y": 300.0,
             "hp": 270, "helmet_hp": 0, "shield_hp": 0, "balloon_hp": 0},
        ])

        zombies = to_json_record(build_state(raw))["zombies"]

        by_type = {zombie["type_code"]: zombie for zombie in zombies}
        self.assertEqual(by_type[2]["total_hp"], 640)
        self.assertEqual((by_type[2]["body_hp"], by_type[2]["helmet_hp"]), (270, 370))
        self.assertEqual(by_type[4]["total_hp"], 1370)
        self.assertEqual((by_type[4]["body_hp"], by_type[4]["helmet_hp"]), (270, 1100))
        self.assertEqual(by_type[6]["total_hp"], 1370)
        self.assertEqual((by_type[6]["body_hp"], by_type[6]["shield_hp"]), (270, 1100))
        self.assertEqual(by_type[0]["total_hp"], 270)

    def test_unknown_armor_component_keeps_total_unknown_and_hp_legacy_body_value(self):
        raw = sample(zombies=[{
            "type": 4, "row": 2, "x": 680.0, "y": 250.0,
            "hp": 270, "helmet_hp": None, "shield_hp": 0, "balloon_hp": 0,
        }])

        zombie = to_json_record(build_state(raw))["zombies"][0]

        self.assertEqual(zombie["hp"], 270)
        self.assertEqual(zombie["body_hp"], 270)
        self.assertIsNone(zombie["helmet_hp"])
        self.assertIsNone(zombie["total_hp"])

    def test_progress_maps_codes_keeps_unknowns_and_reports_per_field_evidence(self):
        raw = sample()
        raw["candidates"]["game_progress"]["raw_candidate_fields"] = {
            "scene": {"value": 3, "evidence_level": "observed_once"},
            "mode": {"value": 0, "evidence_level": "observed_once"},
            "background": {"value": 2, "evidence_level": "observed_once"},
            "level": {"value": 5, "evidence_level": "observed_once"},
            "current_wave": {"value": 3, "evidence_level": "observed_once"},
            "total_waves": {"value": 20, "evidence_level": "observed_once"},
            "pause_flag": {"value": 1, "evidence_level": "observed_once"},
            "won_flag": {"value": 0, "evidence_level": "observed_once"},
        }

        record = to_json_record(build_state(raw))

        self.assertEqual(record["game"]["scene"], "playing")
        self.assertEqual(record["game"]["phase"], "playing")
        self.assertEqual(record["game"]["scene_code"], 3)
        self.assertEqual(record["game"]["mode"], "adventure")
        self.assertEqual(record["game"]["mode_code"], 0)
        self.assertEqual(record["game"]["background"], "pool")
        self.assertEqual(record["game"]["level"], "1-5")
        self.assertEqual(record["game"]["level_number"], 5)
        self.assertEqual(record["game"]["spawned_waves"], 3)
        self.assertEqual(record["game"]["total_waves"], 20)
        self.assertIs(record["game"]["paused"], True)
        self.assertIs(record["game"]["level_complete"], False)
        for key in ("game.scene", "game.phase", "game.mode", "game.background",
                    "game.level", "game.wave", "game.total_waves", "game.paused",
                    "game.level_complete"):
            self.assertEqual(record["availability"][key], "provisional")
            self.assertEqual(record["evidence"][key], "observed_once")

        raw["candidates"]["game_progress"]["raw_candidate_fields"].update({
            "scene": {"value": 99}, "mode": {"value": 999}, "background": {"value": 999},
        })
        unknown = to_json_record(build_state(raw))["game"]
        self.assertIsNone(unknown["scene"])
        self.assertEqual(unknown["scene_code"], 99)
        self.assertIsNone(unknown["mode"])
        self.assertEqual(unknown["mode_code"], 999)
        self.assertIsNone(unknown["background"])
        self.assertEqual(unknown["background_code"], 999)

    def test_menu_scene_hides_stale_board_progress_and_preserves_raw_values(self):
        raw = sample()
        raw["candidates"]["game_progress"]["raw_candidate_fields"] = {
            "scene": {"value": 1}, "mode": {"value": 0},
            "background": {"value": 0}, "level": {"value": 5},
            "current_wave": {"value": 3}, "total_waves": {"value": 20},
            "pause_flag": {"value": 1}, "won_flag": {"value": 0},
        }

        record = to_json_record(build_state(raw))

        self.assertEqual(record["game"]["phase"], "menu")
        self.assertEqual(record["game"]["mode"], "adventure")
        self.assertIsNone(record["game"]["level"])
        self.assertIsNone(record["game"]["spawned_waves"])
        self.assertIsNone(record["game"]["paused"])
        self.assertIsNone(record["game"]["level_complete"])
        self.assertEqual(record["availability"]["game.level"], "unavailable")
        self.assertEqual(record["availability"]["game.wave"], "unavailable")
        self.assertEqual(record["game"]["progress_raw"]["level"]["value"], 5)

    def test_adventure_level_labels_roll_over_after_each_ten_levels(self):
        for raw_level, expected_label in ((15, "2-5"), (50, "5-10")):
            with self.subTest(raw_level=raw_level):
                raw = sample()
                raw["candidates"]["game_progress"]["raw_candidate_fields"] = {
                    "scene": {"value": 3},
                    "mode": {"value": 0},
                    "level": {"value": raw_level},
                }

                game = to_json_record(build_state(raw))["game"]

                self.assertEqual(game["level"], expected_label)
                self.assertEqual(game["level_number"], raw_level)
                self.assertEqual(game["level_raw_code"], raw_level)

    def test_progress_flags_reject_wide_legacy_values_instead_of_truthiness(self):
        raw = sample()
        raw["candidates"]["game_progress"]["raw_candidate_fields"] = {
            "scene": {"value": 3}, "mode": {"value": 0},
            "pause_flag": {"value": 473956353}, "won_flag": {"value": 4284372992},
        }

        record = to_json_record(build_state(raw))

        self.assertIsNone(record["game"]["paused"])
        self.assertIsNone(record["game"]["level_complete"])
        self.assertEqual(record["game"]["pause_raw_code"], 473956353)
        self.assertEqual(record["game"]["level_complete_raw_code"], 4284372992)
        self.assertEqual(record["availability"]["game.paused"], "error")
        self.assertEqual(record["availability"]["game.level_complete"], "error")

    def test_empty_arrays_are_empty_provisional_lists_and_missing_fields_stay_null(self):
        record = to_json_record(build_state(sample()))

        self.assertTrue(record["valid"])
        self.assertEqual(record["plants"], [])
        self.assertEqual(record["zombies"], [])
        self.assertEqual(record["items"], [])
        self.assertEqual(record["availability"]["zombies"], "provisional")
        self.assertIsNone(record["game"]["level"])
        self.assertEqual(record["availability"]["game.level"], "unavailable")
        self.assertEqual(record["board"]["plantability"][0][0], "unknown")

    def test_unmapped_zombie_keeps_its_code_without_inventing_a_name(self):
        raw = sample(zombies=[{"type": 999, "row": 0, "x": 650.0, "y": 150.0, "hp": 100}])
        record = to_json_record(build_state(raw))
        self.assertEqual(record["zombies"][0]["type_code"], 999)
        self.assertEqual(record["zombies"][0]["type_name"], "unknown")

    def test_silver_coin_and_unknown_item_names(self):
        raw = sample(items=[
            {"type": 1, "x": 581.0, "y": 322.0},
            {"type": 999, "x": 500.0, "y": 300.0},
        ])
        record = to_json_record(build_state(raw))
        self.assertEqual(record["items"][0]["type_name"], "silver_coin")
        self.assertEqual(record["items"][0]["type_meaning"], "candidate")
        self.assertEqual(record["items"][1]["type_name"], "unknown")
        self.assertEqual(record["items"][1]["type_meaning"], "unknown")

    def test_invalid_plant_and_count_mismatch_are_explicit_errors(self):
        for type_code, row, column in ((1, 5, 2), (1, 1, 9), (-1, 1, 2), (999, 1, 2)):
            with self.subTest(type_code=type_code, row=row, column=column):
                invalid = sample(plants=[{"type": type_code, "row": row, "column": column}])
                invalid_state = to_json_record(build_state(invalid))
                self.assertFalse(invalid_state["valid"])
                self.assertEqual(invalid_state["availability"]["plants"], "error")
                self.assertIsNone(invalid_state["plants"])
                self.assertIsNone(invalid_state["board"]["cells"][1][2])

        inconsistent_plants = sample(plants=[{"type": 1, "row": 1, "column": 2}])
        inconsistent_plants["arrays"]["plants"]["reported_live_count"] = 2
        mismatch_state = to_json_record(build_state(inconsistent_plants))
        self.assertFalse(mismatch_state["valid"])
        self.assertEqual(mismatch_state["availability"]["plants"], "error")
        self.assertIsNone(mismatch_state["plants"])
        self.assertIsNone(mismatch_state["board"]["cells"][1][2])

        inconsistent = sample()
        inconsistent["arrays"]["zombies"]["reported_live_count"] = 1
        inconsistent_state = to_json_record(build_state(inconsistent))
        self.assertFalse(inconsistent_state["valid"])
        self.assertEqual(inconsistent_state["availability"]["zombies"], "error")
        self.assertIsNone(inconsistent_state["zombies"])

    def test_read_failure_is_distinct_from_a_successful_empty_array(self):
        raw = sample()
        raw["arrays"]["plants"] = {"status": "unavailable", "error": "short read at candidate array"}

        record = to_json_record(build_state(raw))

        self.assertEqual(record["plants"], None)
        self.assertEqual(record["availability"]["plants"], "error")
        self.assertEqual(record["availability"]["board.occupancy"], "error")
        self.assertIn("short read", record["errors"][0]["message"])
        self.assertEqual(record["zombies"], [])
        self.assertEqual(record["items"], [])
        self.assertEqual(record["availability"]["items"], "provisional")

    def test_process_exit_produces_a_disconnected_error_snapshot(self):
        def exited():
            raise TargetNotRunningError("No running process found for target.")

        record = capture_state(raw_reader=exited)

        self.assertEqual(record["status"], "disconnected")
        self.assertFalse(record["valid"])
        self.assertEqual(record["availability"]["sun_balance"], "error")
        self.assertIsNone(record["sun_balance"])

    def test_capture_retries_once_after_an_inconsistent_sample(self):
        bad = sample()
        bad["arrays"]["plants"]["reported_live_count"] = 1
        good = sample()
        values = iter([(bad, {}), (good, {})])

        record = capture_state(raw_reader=lambda: next(values))

        self.assertTrue(record["valid"])
        self.assertEqual(record["retry_count"], 1)
        self.assertGreaterEqual(record["sample_sequence"], 1)


if __name__ == "__main__":
    unittest.main()
