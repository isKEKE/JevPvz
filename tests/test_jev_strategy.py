"""Fixed-State checks for the strategy feature/signal layer.

No game access, no network, no clock: every case is built from literal State
projections so the OD-22 key matrix (V35) and the OD-30 urgency table (V36)
stay reproducible offline.
"""

import unittest

from configs.plant_catalog import PLANT_ENGAGEMENTS, PLANT_ROLES, PLANTS, PlantInfo, plant_info
from jev.strategy import (
    BRANCH_COLLECT,
    BRANCH_PLANT,
    ECONOMY_SIGNALS,
    PHASES,
    URGENCY_BANDS,
    build_branch_state_key,
    build_collect_branch_state_key,
    build_plant_candidates,
    evaluate_strategy,
    management_facts,
    urgency_band,
)


def card(type_code, type_name, cost, *, slot=0, usable=True, cooldown_ready=True):
    return {
        "slot": slot,
        "type_code": type_code,
        "type_name": type_name,
        "cost": cost,
        "cooldown_ready": cooldown_ready,
        "usable": usable,
    }


def plant(type_code, type_name, row, col):
    return {"type_code": type_code, "type_name": type_name, "row": row, "col": col}


def zombie(row, *, hp=100, distance=None):
    entry = {
        "type_code": 0,
        "type_name": "normal_zombie",
        "row": row,
        "x": 0,
        "y": 0,
        "hp": hp,
    }
    if distance is not None:
        entry["distance_to_house_cells"] = distance
    return entry


def item(type_code, x, y, type_name="sun"):
    return {"type_code": type_code, "type_name": type_name, "x": x, "y": y}


def empty_cells():
    return [[None for _ in range(9)] for _ in range(5)]


def jev_state(*, sun_balance=50, cards=None, plants=None, zombies=None, cells=None, items=None, **metadata):
    state = {
        "schema_version": 1,
        "observed_at_utc": "2026-09-27T10:00:00Z",
        "sample_sequence": 2104,
        "status": "ok",
        "valid": True,
        "decision_ready": True,
        "game": {
            "phase": "playing",
            "mode": "adventure",
            "background": "day",
            "paused": False,
            "level": 1,
            "wave": 1,
            "total_waves": 20,
            "level_complete": False,
        },
        "sun_balance": sun_balance,
        "board": {"rows": 5, "cols": 9, "cells": empty_cells() if cells is None else cells},
        "plants": [] if plants is None else plants,
        "zombies": [] if zombies is None else zombies,
        "lanes": [],
        "items": [] if items is None else items,
        "cards": [] if cards is None else cards,
    }
    state.update(metadata)
    return state


def plant_key(state):
    return build_branch_state_key(BRANCH_PLANT, state)


def keys_of(payload):
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield key
            yield from keys_of(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from keys_of(value)


class UrgencyBandTests(unittest.TestCase):
    """V36 — the OD-22/OD-30 table, asserted entry by entry."""

    EXPECTED = {
        1: {0: "critical", 1: "critical", 2: "high", 3: "high", 4: "medium", 5: "medium", 6: "low", 7: "low", 8: "low"},
        2: {0: "critical", 1: "critical", 2: "high", 3: "high", 4: "medium", 5: "medium", 6: "low", 7: "low", 8: "low"},
        3: {0: "critical", 1: "critical", 2: "critical", 3: "critical", 4: "high", 5: "high", 6: "low", 7: "low", 8: "low"},
    }

    def test_threshold_table_for_counts_one_two_and_three(self):
        for zombie_count, bands in self.EXPECTED.items():
            for nearest_cells, expected in bands.items():
                with self.subTest(zombie_count=zombie_count, nearest_cells=nearest_cells):
                    self.assertEqual(urgency_band(zombie_count, nearest_cells), expected)

    def test_more_zombies_promote_the_band_at_the_same_distance(self):
        self.assertEqual(urgency_band(4, 4), "high")
        self.assertEqual(urgency_band(3, 4), "high")
        self.assertEqual(urgency_band(2, 4), "medium")
        self.assertEqual(urgency_band(3, 2), "critical")
        self.assertEqual(urgency_band(2, 2), "high")

    def test_zero_zombies_or_unknown_distance_is_none(self):
        for nearest_cells in range(0, 9):
            with self.subTest(nearest_cells=nearest_cells):
                self.assertEqual(urgency_band(0, nearest_cells), "none")
        self.assertEqual(urgency_band(3, None), "none")

    def test_every_band_is_from_the_ordered_closed_set(self):
        for zombie_count in (0, 1, 2, 3, 7):
            for nearest_cells in (*range(0, 9), None):
                with self.subTest(zombie_count=zombie_count, nearest_cells=nearest_cells):
                    self.assertIn(urgency_band(zombie_count, nearest_cells), URGENCY_BANDS)


class PlantBranchKeyTests(unittest.TestCase):
    """V35 — stability and sensitivity of the OD-22 PlantBranch key."""

    def setUp(self):
        self.cards = [card(0, "peashooter", 100, slot=0), card(1, "sunflower", 50, slot=1)]

    def test_sun_50_to_75_with_unchanged_affordable_set_keeps_key(self):
        state_50 = jev_state(sun_balance=50, cards=self.cards)
        state_75 = jev_state(sun_balance=75, cards=self.cards)
        self.assertEqual(evaluate_strategy(state_50).affordable, frozenset({"sunflower"}))
        self.assertEqual(evaluate_strategy(state_75).affordable, frozenset({"sunflower"}))
        self.assertEqual(plant_key(state_50), plant_key(state_75))

    def test_sun_75_to_100_that_changes_affordable_set_changes_key(self):
        state_75 = jev_state(sun_balance=75, cards=self.cards)
        state_100 = jev_state(sun_balance=100, cards=self.cards)
        self.assertEqual(evaluate_strategy(state_100).affordable, frozenset({"peashooter", "sunflower"}))
        self.assertNotEqual(plant_key(state_75), plant_key(state_100))

    def test_distance_move_inside_one_band_keeps_key(self):
        state_5 = jev_state(zombies=[zombie(0, distance=5)])
        state_4 = jev_state(zombies=[zombie(0, distance=4)])
        self.assertEqual(evaluate_strategy(state_5).rows[0].urgency, "medium")
        self.assertEqual(evaluate_strategy(state_4).rows[0].urgency, "medium")
        self.assertEqual(plant_key(state_5), plant_key(state_4))

    def test_distance_crossing_a_band_changes_key(self):
        state_4 = jev_state(zombies=[zombie(0, distance=4)])
        state_3 = jev_state(zombies=[zombie(0, distance=3)])
        self.assertEqual(evaluate_strategy(state_4).rows[0].urgency, "medium")
        self.assertEqual(evaluate_strategy(state_3).rows[0].urgency, "high")
        self.assertNotEqual(plant_key(state_4), plant_key(state_3))

    def test_zombie_count_change_changes_key_inside_one_band(self):
        one = jev_state(zombies=[zombie(0, distance=5)])
        two = jev_state(zombies=[zombie(0, distance=5), zombie(0, distance=7)])
        self.assertEqual(evaluate_strategy(one).rows[0].urgency, "medium")
        self.assertEqual(evaluate_strategy(two).rows[0].urgency, "medium")
        self.assertNotEqual(plant_key(one), plant_key(two))

    def test_attacker_count_change_changes_key(self):
        one_attacker = jev_state(plants=[plant(0, "peashooter", 0, 0)])
        two_attackers = jev_state(plants=[plant(0, "peashooter", 0, 0), plant(0, "peashooter", 0, 1)])
        self.assertNotEqual(plant_key(one_attacker), plant_key(two_attackers))
        self.assertNotEqual(plant_key(one_attacker), plant_key(jev_state()))

    def test_non_attacker_plant_does_not_change_attacker_count(self):
        without = jev_state()
        with_sunflower = jev_state(plants=[plant(1, "sunflower", 0, 0)])
        self.assertEqual(evaluate_strategy(with_sunflower).rows[0].attacker_count, 0)
        self.assertEqual(plant_key(without), plant_key(with_sunflower))

    def test_defender_presence_changes_key(self):
        without = jev_state()
        with_wall_nut = jev_state(plants=[plant(3, "wall_nut", 0, 0)])
        self.assertTrue(evaluate_strategy(with_wall_nut).rows[0].has_defender)
        self.assertNotEqual(plant_key(without), plant_key(with_wall_nut))

    def test_occupied_cell_change_changes_key(self):
        cells = empty_cells()
        empty_state = jev_state(cells=cells)
        filled_cells = empty_cells()
        filled_cells[2][3] = "plant:repeater"
        filled_state = jev_state(cells=filled_cells, plants=[plant(7, "repeater", 2, 3)])
        self.assertNotEqual(plant_key(empty_state), plant_key(filled_state))

    def test_metadata_and_raw_distance_and_raw_hp_do_not_change_key(self):
        base = jev_state(
            cards=self.cards,
            zombies=[zombie(0, hp=100, distance=5)],
            sample_sequence=2104,
            observed_at_utc="2026-09-27T10:00:00Z",
            identity_verified_at_utc="2026-09-27T10:00:00Z",
            latency_ms=676,
        )
        changed = jev_state(
            cards=self.cards,
            zombies=[zombie(0, hp=60, distance=5.4)],
            sample_sequence=9999,
            observed_at_utc="2026-09-27T10:00:07Z",
            identity_verified_at_utc="2026-09-27T10:00:06Z",
            latency_ms=12,
        )
        base_signals = evaluate_strategy(base)
        changed_signals = evaluate_strategy(changed)
        self.assertNotEqual(base_signals.rows[0].hp_total, changed_signals.rows[0].hp_total)
        self.assertEqual(base_signals.rows[0].urgency, changed_signals.rows[0].urgency)
        self.assertEqual(plant_key(base), plant_key(changed))

    def test_key_is_hashable_and_equal_for_equivalent_states(self):
        first = plant_key(jev_state(cards=self.cards, zombies=[zombie(0, distance=2, hp=300)]))
        second = plant_key(jev_state(cards=self.cards, zombies=[zombie(0, distance=2, hp=10)]))
        self.assertEqual(len({first, second}), 1)
        self.assertIsInstance(hash(first), int)


class WaveZeroPlantBranchKeyTests(unittest.TestCase):
    """V60/OD-45: at ``wave == 0`` the zombie components leave the plant key."""

    def test_wave_zero_ignores_a_whole_zombie_batch_appearing_or_vanishing(self):
        # The measured cold-start transient: 9 zombies the moment the level opens,
        # gone 0.93 s later. It must not move the plant key while wave is 0.
        nine = jev_state(game={"wave": 0}, zombies=[zombie(0, distance=8) for _ in range(9)])
        none = jev_state(game={"wave": 0}, zombies=[])
        self.assertEqual(evaluate_strategy(nine).rows[0].zombie_count, 9)
        self.assertEqual(plant_key(nine), plant_key(none))

    def test_wave_zero_still_sends_the_zombies_to_the_model(self):
        nine = jev_state(game={"wave": 0}, zombies=[zombie(0, distance=8) for _ in range(9)])
        # The guard only changes key sensitivity; the fact stays visible.
        self.assertEqual(len(management_facts(nine, None)["zombies"]), 9)

    def test_wave_one_keeps_the_zombie_components_in_the_key(self):
        threatened = jev_state(game={"wave": 1}, zombies=[zombie(0, distance=8)])
        empty = jev_state(game={"wave": 1}, zombies=[])
        self.assertNotEqual(plant_key(threatened), plant_key(empty))

    def test_missing_or_unparseable_wave_is_conservative(self):
        threatened = jev_state(zombies=[zombie(0, distance=8)])
        empty = jev_state(zombies=[])
        del threatened["game"]["wave"]
        del empty["game"]["wave"]
        self.assertNotEqual(plant_key(threatened), plant_key(empty))
        without_game = jev_state(zombies=[zombie(0, distance=8)])
        without_game.pop("game")
        without_game_empty = jev_state(zombies=[])
        without_game_empty.pop("game")
        self.assertNotEqual(plant_key(without_game), plant_key(without_game_empty))
        string_wave = jev_state(game={"wave": "0"}, zombies=[zombie(0, distance=8)])
        self.assertNotEqual(plant_key(string_wave), plant_key(jev_state(game={"wave": "0"}, zombies=[])))


class CollectBranchKeyTests(unittest.TestCase):
    """V42 — the OD-32 CollectBranch key: visible item types and counts only.

    The key answers one question: did the set of collectable items change? Item
    coordinates are deliberately excluded, because a dropped item keeps falling for
    the whole JEV round trip (measured 263-507 ms against a 20 px fall, i.e. three
    8 px cells), so the old coordinate-bucketed key changed on every sample and
    every already answered collect decision was discarded as superseded.
    """

    def test_the_measured_fall_never_changes_the_key(self):
        # One real sun from .log/test.jsonl: x constant, y 241.5695 -> 261.6696,
        # i.e. exactly the motion that used to flip the bucket from 30 to 33.
        high = jev_state(items=[item(3, x=546.0, y=241.5695037841797)])
        low = jev_state(items=[item(3, x=546.0, y=261.6695861816406)])
        self.assertEqual(build_collect_branch_state_key(high), build_collect_branch_state_key(low))
        self.assertEqual(build_collect_branch_state_key(high), frozenset({(3, 1)}))

    def test_metadata_and_coordinate_churn_never_changes_the_key(self):
        base = jev_state(items=[item(3, x=40, y=80), item(4, x=120, y=64)])
        noisy = jev_state(
            items=[item(3, x=41, y=99), item(4, x=119, y=20)],
            sample_sequence=9001,
            latency_ms=11,
            observed_at_utc="2026-09-27T10:00:05Z",
        )
        self.assertEqual(build_collect_branch_state_key(base), build_collect_branch_state_key(noisy))
        self.assertEqual(build_collect_branch_state_key(base), frozenset({(3, 1), (4, 1)}))

    def test_appearing_disappearing_and_type_changes_do_change_the_key(self):
        one = jev_state(items=[item(3, x=40, y=80)])
        two = jev_state(items=[item(3, x=40, y=80), item(3, x=900, y=4)])
        other_type = jev_state(items=[item(4, x=40, y=80)])
        for left, right in ((one, two), (one, other_type), (two, other_type)):
            self.assertNotEqual(
                build_collect_branch_state_key(left), build_collect_branch_state_key(right)
            )
        self.assertEqual(build_collect_branch_state_key(one), frozenset({(3, 1)}))
        self.assertEqual(build_collect_branch_state_key(two), frozenset({(3, 2)}))

    def test_a_replacement_item_that_keeps_types_and_counts_keeps_the_key(self):
        # OD-32 binds the target by item id, so replacing one sun with a different
        # sun cannot strand a decision that is already in flight.
        first = jev_state(items=[item(3, x=40, y=80)])
        replacement = jev_state(items=[item(3, x=700, y=12)])
        self.assertEqual(build_collect_branch_state_key(first), build_collect_branch_state_key(replacement))
        self.assertNotEqual(
            build_collect_branch_state_key(first),
            build_collect_branch_state_key(jev_state(items=[item(3, x=40, y=80), item(3, x=700, y=12)])),
        )

    def test_missing_items_or_unprojectable_items_yield_empty_key(self):
        state = jev_state(items=[item(3, x=40, y=80)])
        state["items"] = None
        self.assertEqual(build_collect_branch_state_key(state), frozenset())
        self.assertEqual(build_collect_branch_state_key(jev_state(items=[{"type_code": None, "x": None, "y": None}])), frozenset())
        # An item without finite coordinates can never be offered as an option, so
        # it must not move the key either.
        self.assertEqual(
            build_collect_branch_state_key(jev_state(items=[item(3, x=40, y=80), item(4, x=None, y=80)])),
            frozenset({(3, 1)}),
        )

    def test_negative_type_code_is_skipped(self):
        self.assertEqual(build_collect_branch_state_key(jev_state(items=[item(-1, x=1, y=2)])), frozenset())

    def test_key_is_hashable(self):
        key = build_collect_branch_state_key(jev_state(items=[item(3, x=40, y=80)]))
        self.assertIsInstance(hash(key), int)

    def test_branch_dispatch_selects_the_documented_key_and_rejects_other_branches(self):
        state = jev_state(items=[item(3, x=40, y=80)])
        self.assertEqual(build_branch_state_key(BRANCH_COLLECT, state), build_collect_branch_state_key(state))
        self.assertEqual(build_branch_state_key(BRANCH_PLANT, state), plant_key(state))
        with self.assertRaises(ValueError):
            build_branch_state_key("shovel", state)


class PlantCatalogRoleTests(unittest.TestCase):
    def test_all_49_plants_have_a_role_from_the_closed_set(self):
        self.assertEqual(len(PLANTS), 49)
        for entry in PLANTS:
            with self.subTest(plant=entry.name):
                self.assertIn(entry.role, PLANT_ROLES)
        self.assertEqual({entry.role for entry in PLANTS}, set(PLANT_ROLES))

    def test_role_is_the_last_field_and_existing_facts_are_intact(self):
        self.assertEqual(PlantInfo._fields, ("name", "cost", "description_en", "role", "engagement"))
        # V75: engagement is annotated for all 49 plants from a closed set, and the
        # economy plants are the ones whose role is resource (no second axis for it).
        for entry in PLANTS:
            with self.subTest(plant=entry.name):
                self.assertIn(entry.engagement, PLANT_ENGAGEMENTS)
        self.assertEqual(
            {entry.name for entry in PLANTS if entry.engagement == "melee"},
            {"chomper", "squash", "tangle_kelp", "spikeweed", "spikerock", "gloom_shroom"},
        )
        self.assertTrue(
            all(entry.engagement == "none" for entry in PLANTS if entry.role == "resource")
        )
        self.assertEqual(len({entry.name for entry in PLANTS}), 49)
        for entry in PLANTS:
            with self.subTest(plant=entry.name):
                self.assertTrue(entry.name)
                self.assertTrue(entry.description_en.strip())
                self.assertTrue(entry.description_en.isascii())
        self.assertEqual(plant_info(0), PLANTS[0])
        self.assertEqual(plant_info(0).name, "peashooter")
        self.assertEqual(plant_info(0).cost, 100)
        self.assertEqual(plant_info(1).name, "sunflower")
        self.assertEqual(plant_info(1).cost, 50)
        self.assertEqual(plant_info(8).cost, 0)
        self.assertIsNone(plant_info(48).cost)
        self.assertEqual(plant_info(48).name, "imitater")
        self.assertIsNone(plant_info("0"))
        self.assertIsNone(plant_info(49))

    def test_economy_plants_are_the_only_resource_role_holders(self):
        resource_names = {entry.name for entry in PLANTS if entry.role == "resource"}
        self.assertEqual(resource_names, {"sunflower", "sun_shroom", "twin_sunflower", "marigold", "gold_magnet"})
        defender_names = {entry.name for entry in PLANTS if entry.role == "defender"}
        self.assertEqual(defender_names, {"wall_nut", "tall_nut", "pumpkin", "umbrella_leaf"})


class ResourceSignalTests(unittest.TestCase):
    def test_affordable_requires_payable_usable_and_ready(self):
        cards = [
            card(1, "sunflower", 50, slot=0),
            card(0, "peashooter", 100, slot=1),
            card(2, "cherry_bomb", 50, slot=2, usable=False),
            card(3, "wall_nut", 50, slot=3, cooldown_ready=False),
            card(4, "potato_mine", 25, slot=4),
        ]
        signals = evaluate_strategy(jev_state(sun_balance=50, cards=cards))
        self.assertEqual(signals.sun, 50)
        self.assertEqual(signals.affordable, frozenset({"sunflower", "potato_mine"}))
        self.assertIn(signals.economy_signal, ECONOMY_SIGNALS)

    def test_unknown_sun_or_missing_cards_yield_no_affordable_type(self):
        state = jev_state(sun_balance=None, cards=[card(1, "sunflower", 50)])
        self.assertIsNone(evaluate_strategy(state).sun)
        self.assertEqual(evaluate_strategy(state).affordable, frozenset())
        state["cards"] = None
        self.assertEqual(evaluate_strategy(state).affordable, frozenset())
        self.assertEqual(evaluate_strategy(state).economy_signal, "hold")

    def test_economy_signal_uses_only_the_current_sample(self):
        expand = evaluate_strategy(jev_state(sun_balance=50, cards=[card(1, "sunflower", 50)]))
        hold = evaluate_strategy(jev_state(sun_balance=25, cards=[card(1, "sunflower", 50)]))
        stop = evaluate_strategy(jev_state(sun_balance=500, cards=[card(0, "peashooter", 100)]))
        self.assertEqual(expand.economy_signal, "expand")
        self.assertEqual(hold.economy_signal, "hold")
        self.assertEqual(stop.economy_signal, "stop")

    def test_signals_expose_no_predicted_or_reserved_resource_fields(self):
        cards = [card(1, "sunflower", 50), card(0, "peashooter", 100)]
        payload = evaluate_strategy(jev_state(sun_balance=50, cards=cards, zombies=[zombie(0, distance=4)])).to_dict()
        self.assertEqual(
            set(payload),
            {"sun", "affordable", "economy_signal", "phase", "rows", "empty_plantable_cells", "occupied_cells"},
        )
        forbidden = ("project", "reserve", "expect", "forecast", "future", "predict", "income", "rate", "dps", "probability")
        for key in keys_of(payload):
            for word in forbidden:
                with self.subTest(key=key, word=word):
                    self.assertNotIn(word, key.lower())
        self.assertIn(payload["phase"], PHASES)


class RowSignalTests(unittest.TestCase):
    def test_row_components_are_computed_in_code(self):
        state = jev_state(
            plants=[
                plant(0, "peashooter", 2, 0),
                plant(3, "wall_nut", 2, 1),
                plant(1, "sunflower", 2, 2),
                plant(0, "peashooter", 0, 0),
            ],
            zombies=[zombie(2, hp=100, distance=4), zombie(2, hp=60, distance=6)],
        )
        rows = evaluate_strategy(state).rows
        self.assertEqual(len(rows), 5)
        threatened = rows[2]
        self.assertEqual(threatened.zombie_count, 2)
        self.assertEqual(threatened.nearest_cells, 4)
        self.assertEqual(threatened.hp_total, 160)
        self.assertEqual(threatened.attacker_count, 1)
        self.assertTrue(threatened.has_defender)
        self.assertEqual(threatened.urgency, "medium")
        empty = rows[1]
        self.assertEqual(empty.zombie_count, 0)
        self.assertIsNone(empty.nearest_cells)
        self.assertEqual(empty.hp_total, 0)
        self.assertEqual(empty.attacker_count, 0)
        self.assertFalse(empty.has_defender)
        self.assertEqual(empty.urgency, "none")

    def test_unknown_facts_stay_none_instead_of_being_guessed(self):
        state = jev_state()
        state["zombies"] = None
        state["plants"] = None
        state["board"]["cells"] = None
        signals = evaluate_strategy(state)
        self.assertIsNone(signals.empty_plantable_cells)
        for row in signals.rows:
            with self.subTest(row=row.row):
                self.assertIsNone(row.zombie_count)
                self.assertIsNone(row.nearest_cells)
                self.assertIsNone(row.hp_total)
                self.assertIsNone(row.attacker_count)
                self.assertIsNone(row.has_defender)
                self.assertEqual(row.urgency, "none")

    def test_zombie_with_unreadable_hp_or_unknown_plant_role_is_unknown(self):
        no_hp = jev_state(zombies=[{"type_code": 0, "type_name": "normal_zombie", "row": 1, "distance_to_house_cells": 6}])
        self.assertIsNone(evaluate_strategy(no_hp).rows[1].hp_total)
        unknown_role = jev_state(plants=[plant(999, "future_plant", 1, 0)])
        self.assertIsNone(evaluate_strategy(unknown_role).rows[1].attacker_count)
        self.assertIsNone(evaluate_strategy(unknown_role).rows[1].has_defender)

    def test_empty_plantable_cells_skip_unplantable_and_occupied_cells(self):
        cells = empty_cells()
        cells[0][0] = False
        cells[1][1] = "plant:peashooter"
        cells[2][2] = "unknown"
        signals = evaluate_strategy(jev_state(cells=cells))
        self.assertEqual(len(signals.empty_plantable_cells), 42)
        self.assertNotIn((0, 0), signals.empty_plantable_cells)
        self.assertNotIn((1, 1), signals.empty_plantable_cells)
        self.assertNotIn((2, 2), signals.empty_plantable_cells)
        self.assertEqual(signals.occupied_cells, frozenset({(1, 1, "plant:peashooter")}))


class PhaseSignalTests(unittest.TestCase):
    def phase_for(self, state):
        phase = evaluate_strategy(state).phase
        self.assertIn(phase, PHASES)
        return phase

    def test_lane_urgency_drives_the_phase(self):
        self.assertEqual(self.phase_for(jev_state(zombies=[zombie(0, distance=1)])), "emergency")
        self.assertEqual(self.phase_for(jev_state(zombies=[zombie(0, distance=3)])), "defense")
        self.assertEqual(self.phase_for(jev_state(zombies=[zombie(0, distance=4)])), "recovery")
        self.assertEqual(self.phase_for(jev_state(zombies=[zombie(0, distance=7)])), "development")

    def test_clear_lawn_splits_economy_from_development(self):
        expanding = jev_state(sun_balance=50, cards=[card(1, "sunflower", 50)])
        self.assertEqual(self.phase_for(expanding), "economy")
        no_resource_card = jev_state(sun_balance=500, cards=[card(0, "peashooter", 100)])
        self.assertEqual(self.phase_for(no_resource_card), "development")
        unaffordable_resource = jev_state(sun_balance=25, cards=[card(1, "sunflower", 50)])
        self.assertEqual(self.phase_for(unaffordable_resource), "development")

    def test_unknown_threat_data_does_not_invent_an_emergency(self):
        state = jev_state(sun_balance=50, cards=[card(1, "sunflower", 50)])
        state["zombies"] = None
        self.assertEqual(self.phase_for(state), "economy")


class PlantCandidateTests(unittest.TestCase):
    def setUp(self):
        self.cells = empty_cells()
        self.cells[0][0] = False
        self.cells[1][1] = "plant:peashooter"
        self.cards = [
            card(1, "sunflower", 50, slot=0),
            card(4, "potato_mine", 25, slot=1),
            card(0, "peashooter", 100, slot=2),
            card(3, "wall_nut", 50, slot=3, cooldown_ready=False),
        ]
        self.state = jev_state(sun_balance=50, cards=self.cards, cells=self.cells)

    def test_candidates_equal_affordable_cross_empty_plantable_cells(self):
        signals = evaluate_strategy(self.state)
        candidates = build_plant_candidates(self.state, signals)
        self.assertEqual(signals.affordable, frozenset({"sunflower", "potato_mine"}))
        self.assertEqual(len(signals.empty_plantable_cells), 43)
        self.assertEqual(len(candidates), 2 * 43)
        positions = {(entry["type_name"], entry["row"], entry["col"]) for entry in candidates}
        self.assertEqual(len(positions), len(candidates))
        self.assertEqual(positions, {
            (type_name, row, col)
            for type_name in signals.affordable
            for row, col in signals.empty_plantable_cells
        })
        self.assertNotIn((0, 0), {(row, col) for _, row, col in positions})
        self.assertNotIn((1, 1), {(row, col) for _, row, col in positions})

    def test_enumeration_order_is_deterministic_and_not_a_ranking(self):
        first = build_plant_candidates(self.state)
        second = build_plant_candidates(self.state)
        self.assertEqual(first, second)
        self.assertEqual(first, sorted(first, key=lambda entry: (entry["type_name"], entry["row"], entry["col"])))
        keys = [(entry["type_name"], entry["row"], entry["col"]) for entry in first]
        self.assertEqual(keys, sorted(keys))

    def test_no_affordable_card_returns_empty_candidates(self):
        unaffordable = jev_state(sun_balance=10, cards=self.cards, cells=self.cells)
        self.assertEqual(evaluate_strategy(unaffordable).affordable, frozenset())
        self.assertEqual(build_plant_candidates(unaffordable), [])

    def test_full_board_or_unknown_board_returns_empty_candidates(self):
        filled = empty_cells()
        for row in range(5):
            for col in range(9):
                filled[row][col] = "plant:peashooter"
        self.assertEqual(build_plant_candidates(jev_state(sun_balance=50, cards=self.cards, cells=filled)), [])
        unknown = jev_state(sun_balance=50, cards=self.cards)
        unknown["board"]["cells"] = None
        self.assertEqual(build_plant_candidates(unknown), [])


if __name__ == "__main__":
    unittest.main()


class ManagementDistanceRevisionTests(unittest.TestCase):
    def test_discrete_approach_changes_key_without_raw_hp_or_subcell_churn(self):
        from jev.strategy import management_state_key
        state = {"zombies": [{"type_name": "normal_zombie", "row": 0, "distance_to_house_cells": 5.9, "hp": 270}]}
        key = management_state_key(state)
        state["zombies"][0].update(distance_to_house_cells=5.1, hp=100)
        self.assertEqual(management_state_key(state), key)
        state["zombies"][0]["distance_to_house_cells"] = 4.9
        self.assertNotEqual(management_state_key(state), key)


class ManagementFactAcceptanceTests(unittest.TestCase):
    def test_waves_need_matching_available_all_state_and_unknown_stays_null(self):
        from jev.strategy import management_facts, management_state_key
        state = jev_state()
        state.update(sample_sequence=1, observed_at_utc="sample")
        state["game"].update(wave=3, total_waves=20)
        source = {"sample_sequence": 1, "observed_at_utc": "sample", "game": dict(state["game"]), "availability": {"game.wave": "available", "game.total_waves": "unavailable"}}
        self.assertEqual(management_facts(state, source)["waves"], {"wave": 3, "total_waves": None})
        self.assertEqual(management_facts(state)["waves"], {"wave": None, "total_waves": None})
        known = management_state_key(state, source)
        source["availability"]["game.wave"] = "error"
        self.assertNotEqual(management_state_key(state, source), known)
        source["availability"]["game.wave"] = "available"; source["sample_sequence"] = 2
        self.assertIsNone(management_facts(state, source)["waves"]["wave"])

    def test_currency_and_lane_counts_are_observations_without_strategy_answers(self):
        from jev.strategy import management_facts
        from configs.plant_catalog import PLANTS
        gold_magnet_code = next(code for code, info in enumerate(PLANTS) if info.name == "gold_magnet")
        state = jev_state(sun_balance=75, cards=[card(0, "peashooter", 100), card(gold_magnet_code, "gold_magnet", 100)], plants=[plant(1, "sunflower", 0, 0)], zombies=[zombie(2, distance=3)])
        facts = management_facts(state)
        self.assertEqual(facts["plant_counts"], {"sunflower": 1})
        self.assertEqual(facts["cards"][0]["shortfall"], 25)
        self.assertIsNone(facts["cards"][1]["production_currency"])
        marigold_code = next(code for code, info in enumerate(PLANTS) if info.name == "marigold")
        state["cards"].append(card(marigold_code, "marigold", 50))
        self.assertEqual(management_facts(state)["cards"][-1]["production_currency"], "coin")
        self.assertEqual(facts["observed_lanes"][2]["zombie_count"], 1)
        self.assertNotIn("urgency", facts["observed_lanes"][2])
        self.assertNotIn("phase", facts)
        state["sun_balance"] = None
        self.assertIsNone(management_facts(state)["cards"][0]["shortfall"])


class LaneCompositionAndColumnSemanticsTests(unittest.TestCase):
    """V64/OD-49/OD-50/R38 — layout facts and column semantics, never answers.

    The run that motivated these fields (``run 92f9a6ac``) showed the model only
    receiving global per-type counts and per-plant coordinates, so it could not
    see per-lane composition or which side of the lawn it was planting toward.
    Only facts are added here: no recommended count, column, or priority.
    """

    def catalog_code(self, name):
        return next(index for index, info in enumerate(PLANTS) if info.name == name)

    def mixed_state(self):
        return jev_state(
            sun_balance=75,
            cards=[
                card(self.catalog_code("sunflower"), "sunflower", 50),
                card(self.catalog_code("peashooter"), "peashooter", 100),
                card(999, "unknown", 25),
            ],
            plants=[
                plant(self.catalog_code("sunflower"), "sunflower", 0, 0),
                plant(self.catalog_code("sunflower"), "sunflower", 0, 1),
                plant(self.catalog_code("peashooter"), "peashooter", 0, 2),
                plant(self.catalog_code("wall_nut"), "wall_nut", 1, 8),
                plant(999, "mystery_plant", 2, 0),
            ],
        )

    def test_lane_composition_counts_each_row_and_keeps_empty_rows_explicit(self):
        facts = management_facts(self.mixed_state())
        self.assertEqual(
            facts["lane_composition"],
            [
                {"row": 0, "resource": 2, "attacker": 1, "defender": 0},
                {"row": 1, "resource": 0, "attacker": 0, "defender": 1},
                {"row": 2, "resource": 0, "attacker": 0, "defender": 0},
                {"row": 3, "resource": 0, "attacker": 0, "defender": 0},
                {"row": 4, "resource": 0, "attacker": 0, "defender": 0},
            ],
        )
        # Consistency with `plants`: a row's class sum is its number of
        # classifiable plants, and row 2's unknown-role plant belongs to no class.
        for entry in facts["lane_composition"]:
            length = len([item_ for item_ in facts["plants"] if item_["row"] == entry["row"]])
            self.assertLessEqual(entry["resource"] + entry["attacker"] + entry["defender"], length)

    def test_lane_composition_is_null_when_plants_are_unavailable_and_zero_when_empty(self):
        state = jev_state()
        state["plants"] = None
        facts = management_facts(state)
        self.assertIsNone(facts["lane_composition"])
        self.assertIsNone(facts["plant_counts"])
        self.assertEqual(
            management_facts(jev_state(plants=[]))["lane_composition"],
            [{"row": row, "resource": 0, "attacker": 0, "defender": 0} for row in range(5)],
        )

    def test_board_column_direction_is_a_fact_that_matches_the_board_geometry(self):
        state = self.mixed_state()
        direction = management_facts(state)["board"]["column_direction"]
        self.assertEqual(direction["house_side_col"], 0)
        self.assertEqual(direction["zombie_side_col"], 8)
        self.assertTrue(direction["increasing_col_moves_toward_zombies"])
        self.assertIn("first_cell_center", direction["geometry"])
        self.assertIn("horizontal_spacing", direction["geometry"])
        # The stated direction agrees with the columns this same board yields.
        columns = {col for _, col in evaluate_strategy(state).empty_plantable_cells}
        self.assertEqual(min(columns), direction["house_side_col"])
        self.assertEqual(max(columns), direction["zombie_side_col"])

    def test_card_roles_come_from_the_catalog_and_unknown_cards_carry_none(self):
        facts = management_facts(self.mixed_state())
        # Every card in hand stays visible; a card the catalog cannot resolve keeps
        # its projected name and cost but never inherits a role or ability text.
        self.assertEqual(
            {card_["type_name"]: card_["role"] for card_ in facts["cards"]},
            {"sunflower": "resource", "peashooter": "attacker", "unknown": None},
        )
        unknown = [card_ for card_ in facts["cards"] if card_["type_name"] == "unknown"][0]
        self.assertIsNone(unknown["description_en"])
        self.assertIsNone(unknown["production_currency"])

    def test_shared_facts_never_carry_a_layout_or_strategy_answer(self):
        facts = management_facts(self.mixed_state())
        banned = ("recommend", "quota", "ideal", "target_count", "goal", "priority", "urgency", "phase", "advice", "should_plant")
        keys = " ".join(str(key) for key in keys_of(facts))
        for word in banned:
            self.assertNotIn(word, keys)


class ThreatLabelFactsTests(unittest.TestCase):
    """The request carries ordered threat labels; no zombie number reaches the model."""

    def test_lane_threat_escalates_a_lane_without_an_attacker(self):
        from jev.strategy import lane_threat_band
        # No attacker in the lane: at least high, and undefended once zombies arrive.
        self.assertEqual(lane_threat_band({"zombie_count": 0, "nearest_cells": None, "attacker_count": 0}), "high")
        self.assertEqual(lane_threat_band({"zombie_count": 2, "nearest_cells": 1, "attacker_count": 0}), "undefended")
        self.assertEqual(lane_threat_band({"zombie_count": 1, "nearest_cells": 7, "attacker_count": 0}), "undefended")
        # With an attacker the plain OD-22 band decides; a missing distance is unknown.
        self.assertEqual(lane_threat_band({"zombie_count": 2, "nearest_cells": 1, "attacker_count": 1}), "critical")
        self.assertEqual(lane_threat_band({"zombie_count": 1, "nearest_cells": 7, "attacker_count": 1}), "low")
        self.assertEqual(lane_threat_band({"zombie_count": 0, "nearest_cells": None, "attacker_count": 1}), "none")
        self.assertEqual(lane_threat_band({"zombie_count": 3, "nearest_cells": None, "attacker_count": 1}), "unknown")

    def test_label_bands_are_ordered_and_closed(self):
        from jev.strategy import armor_band, crowd_band, proximity_band
        self.assertEqual([crowd_band(n) for n in (0, 1, 2, 3, 5, None)],
                         ["none", "single", "pair", "small_group", "horde", "none"])
        self.assertEqual([proximity_band(n) for n in (1, 3, 5, 8, 12, None)],
                         ["at_the_door", "very_close", "close", "midfield", "far", None])
        self.assertEqual(armor_band({"helmet_hp": 0, "shield_hp": 0}), "none")
        self.assertEqual(armor_band({"helmet_hp": 100}), "armored")
        self.assertIsNone(armor_band({"helmet_hp": None, "shield_hp": None}))

    def test_threat_label_facts_replace_every_zombie_number(self):
        import json
        from jev.strategy import threat_label_facts
        facts = {
            "sun": 50,
            "zombies": [{"type_name": "normal_zombie", "row": 2, "distance_to_house_cells": 1, "hp": 270,
                         "body_hp": None, "helmet_hp": None, "shield_hp": None}],
            "observed_lanes": [{"row": 2, "zombie_count": 1, "nearest_cells": 1, "hp_total": 270,
                                "attacker_count": 0, "has_defender": False}],
        }
        labelled = threat_label_facts(facts)
        self.assertEqual(labelled["zombies"], [{"type_name": "normal_zombie", "row": 2,
                                                "proximity": "at_the_door", "armor": None}])
        self.assertEqual(labelled["observed_lanes"], [{"row": 2, "threat": "undefended", "crowd": "single",
                                                      "composition": "normal_zombie", "attacker_count": 0,
                                                      "has_defender": False}])
        text = json.dumps(labelled["zombies"] + labelled["observed_lanes"])
        for number in ("270", "distance", "hp"):
            self.assertNotIn(number, text)
