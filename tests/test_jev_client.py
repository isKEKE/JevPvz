import asyncio
import dataclasses
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typesafe_sdk._core.response_types import ChoiceAnswer, NoulAnswer, Usage
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeClient

from configs.plant_catalog import PLANTS, PlantInfo, plant_info
from configs.zombie_catalog import ZOMBIES, ZOMBIE_NAMES, zombie_info, zombie_name
from jev.client import (
    GLOBAL_IN_FLIGHT_LIMIT,
    REQUEST_TIMEOUT_SECONDS,
    AsyncJevClient,
    JevApiError,
    JevClient,
    build_action_questions,
    build_collect_questions,
    build_plant_questions,
    build_router_questions,
    build_typesafe_state,
)
from jev.config import (
    JevConfigurationError,
    RuntimeConfig,
    load_jev_thresholds,
    load_runtime_config,
    load_typesafe_environment,
    use_configured_http_proxy_fallback,
)
from jev.decision import (
    JevDecisionError,
    combine_collect_decision,
    combine_plant_decision,
    reconcile_router,
    validate_action_answers,
)
from jev.questions import (
    COLLECT_ACT_THRESHOLD,
    COLLECT_NOW_QUESTION_ID,
    COLLECT_QUESTION_SPECS,
    COLLECT_STATE_FIELDS,
    COLLECT_TARGET_QUESTION_ID,
    DISCARD_OPTION_ID,
    MAX_CHOICE_OPTIONS,
    PLANT_EXPERIENCE_PATH,
    PLANT_LANE_QUESTION_ID,
    PLANT_LANE_TARGET_QUESTION_PREFIX,
    PLANT_QUESTION_SPECS,
    PLANT_STATE_FIELDS,
    PLANT_TARGET_QUESTION_ID,
    load_plant_experience,
    plant_lane_question,
    plant_lane_target_question,
    plant_option_id,
    plant_target_question,
)
from jev import client, questions
from jev.strategy import BRANCH_COLLECT, BRANCH_PLANT


def router_response(*, choice="plant", confidence=0.9, collect=0.2, plant=0.8, shovel=0.1):
    remaining = (1.0 - confidence) / 3.0
    choice_probabilities = {key: remaining for key in ("wait", "collect", "plant", "shovel")}
    choice_probabilities[choice] = confidence
    return SimpleNamespace(
        model="jev-latest",
        usage=Usage(input_tokens=100, output_tokens=20),
        answers={
            "should_collect": NoulAnswer(noul=collect),
            "should_plant": NoulAnswer(noul=plant),
            "should_shovel": NoulAnswer(noul=shovel),
            "next_action": ChoiceAnswer(
                choice=choice,
                confidence=confidence,
                probabilities=choice_probabilities,
            ),
        },
    )


def choice_response(answers):
    return SimpleNamespace(
        model="jev-latest",
        usage=Usage(input_tokens=50, output_tokens=10),
        answers=answers,
    )


def jev_state(*, cards=None, items=None, plants=None, zombies=None, cells=None):
    return {
        "schema_version": 1,
        "sample_sequence": 2104,
        "status": "ok",
        "valid": True,
        "decision_ready": True,
        "game": {"phase": "playing", "mode": "adventure", "background": "day", "paused": False},
        "sun_balance": 500,
        "board": {
            "rows": 5,
            "cols": 9,
            "cells": cells if cells is not None else [[False for _ in range(9)] for _ in range(5)],
        },
        "cards": cards if cards is not None else [],
        "plants": plants if plants is not None else [],
        "zombies": zombies if zombies is not None else [],
        "lanes": [],
        "items": items if items is not None else [],
    }


def all_state(*, items=None, **kwargs):
    """The raw All State of the same sample: every item record carries its ``id``.

    Only the All State holds a collectable item's id -- the JEV projection drops it
    on purpose -- so an OD-32 collect decision needs this alongside the projection.
    """
    state = jev_state(items=items, **kwargs)
    state["items"] = [
        {"id": 500 + index, **dict(entry)} for index, entry in enumerate(items or [])
    ]
    state["availability"] = {
        "board.occupancy": "provisional",
        "items": "available",
        "items.position": "available",
    }
    return state


def async_client_environment(**overrides):
    """The credentials the async transport needs, with per-test overrides."""
    environment = {
        "TYPESAFE_API_KEY": "test-key-sentinel",
        "HTTP_PROXY": "http://127.0.0.1:7890",
        "HTTPS_PROXY": "http://127.0.0.1:7890",
    }
    environment.update(overrides)
    return environment


def empty_cells():
    """A five-by-nine board whose cells are all empty and plantable."""
    return [[None for _ in range(9)] for _ in range(5)]


def plant_card(type_code, type_name, cost, *, slot=0):
    return {
        "slot": slot,
        "type_code": type_code,
        "type_name": type_name,
        "cost": cost,
        "cooldown_ready": True,
        "usable": True,
    }


PLANT_CARDS = (
    plant_card(0, "peashooter", 100, slot=0),
    plant_card(1, "sunflower", 50, slot=1),
    plant_card(3, "wall_nut", 50, slot=2),
)
PLANT_CARDS_BEYOND_THE_CAP = (
    plant_card(4, "potato_mine", 25, slot=3),
    plant_card(5, "snow_pea", 175, slot=4),
    plant_card(6, "chomper", 150, slot=5),
)


def plant_type_code(type_name):
    """The seed-pack index the game reports for one catalog plant type."""
    return next(index for index, plant in enumerate(PLANTS) if plant.name == type_name)


def choice_for_question(question, *, choice=None, weights=None, confidence=0.95):
    """Answer one offered Choice, with a concentrated or explicitly weighted distribution."""
    option_ids = list(question.criteria)
    if weights is None:
        chosen = choice or next(key for key in option_ids if key != DISCARD_OPTION_ID)
        remaining = (1.0 - confidence) / max(1, len(option_ids) - 1)
        probabilities = {key: remaining for key in option_ids}
        probabilities[chosen] = confidence
    else:
        chosen = choice or max(weights, key=lambda key: weights[key])
        rest = [key for key in option_ids if key not in weights]
        share = max(0.0, 1.0 - sum(weights.values())) / len(rest) if rest else 0.0
        probabilities = {key: share for key in option_ids}
        probabilities.update(weights)
    return ChoiceAnswer(choice=chosen, confidence=confidence, probabilities=probabilities)


def plant_answer(
    questions,
    *,
    confidence=0.95,
    choice=None,
    weights=None,
    lane=None,
):
    """One complete plant fan-out answer: the offered placement Choice (or lane chain)."""
    answers = {}
    for question_id, question in questions.items():
        if question_id == PLANT_LANE_QUESTION_ID:
            answers[question_id] = choice_for_question(question, choice=lane, confidence=confidence)
        elif question_id.startswith(PLANT_LANE_TARGET_QUESTION_PREFIX):
            answers[question_id] = choice_for_question(question, confidence=confidence)
        elif question_id == PLANT_TARGET_QUESTION_ID:
            answers[question_id] = choice_for_question(
                question, choice=choice, weights=weights, confidence=confidence
            )
    return SimpleNamespace(model="jev-latest", usage=Usage(input_tokens=90, output_tokens=30), answers=answers)


def collect_answer(questions, *, should_collect=0.9, confidence=0.95, choice=None, weights=None):
    answers = {COLLECT_NOW_QUESTION_ID: NoulAnswer(noul=should_collect)}
    return SimpleNamespace(model="jev-latest", usage=Usage(input_tokens=20, output_tokens=4), answers=answers)


def proxy_snapshot():
    return (os.environ.get("ALL_PROXY"), os.environ.get("all_proxy"))


class FakeAsyncTypeSafeClient:
    """An AsyncTypeSafeClient stand-in that records calls and never touches the network."""

    def __init__(self):
        self.calls = []
        self.closed = False
        self.proxy_observations = []
        self.responses = []

    async def system_one(self, **kwargs):
        self.calls.append(kwargs)
        self.proxy_observations.append(proxy_snapshot())
        await asyncio.sleep(0)
        self.proxy_observations.append(proxy_snapshot())
        if self.responses:
            return self.responses.pop(0)
        return SimpleNamespace(model=kwargs.get("model"), usage=Usage(input_tokens=1, output_tokens=1), answers={})

    async def aclose(self):
        self.closed = True


class GatedAsyncTypeSafeClient(FakeAsyncTypeSafeClient):
    """Hold every request until the test releases it, so the in-flight peak is observable."""

    def __init__(self):
        super().__init__()
        self.in_flight = 0
        self.peak_in_flight = 0
        self.limit_reached = asyncio.Event()
        self.release = asyncio.Event()

    async def system_one(self, **kwargs):
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        if self.in_flight >= GLOBAL_IN_FLIGHT_LIMIT:
            self.limit_reached.set()
        try:
            await self.release.wait()
        finally:
            self.in_flight -= 1
        return await super().system_one(**kwargs)


class JevConfigTests(unittest.TestCase):
    def test_dotenv_loads_key_and_both_proxies_without_printing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "TYPESAFE_API_KEY=test-key-sentinel\n"
                "HTTP_PROXY=http://127.0.0.1:7890\n"
                "HTTPS_PROXY=http://127.0.0.1:7890\n"
                "JEV_NOUL_CANDIDATE_THRESHOLD=0.8\n"
                "JEV_ROUTER_CONFIDENCE_THRESHOLD=0.5\n"
                "JEV_ACTION_CONFIDENCE_THRESHOLD=0.7\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                load_typesafe_environment(env_file)
                self.assertEqual(os.environ["TYPESAFE_API_KEY"], "test-key-sentinel")
                self.assertEqual(os.environ["HTTP_PROXY"], "http://127.0.0.1:7890")
                self.assertEqual(os.environ["HTTPS_PROXY"], "http://127.0.0.1:7890")
                thresholds = load_jev_thresholds()
                self.assertEqual(thresholds.noul_candidate_threshold, 0.8)
                self.assertEqual(thresholds.router_confidence_threshold, 0.5)
                self.assertEqual(thresholds.action_confidence_threshold, 0.7)

    def test_thresholds_are_independent_optional_env_values_with_separate_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            thresholds = load_jev_thresholds()
        self.assertEqual(thresholds.noul_candidate_threshold, 0.6)
        self.assertEqual(thresholds.router_confidence_threshold, 0.6)
        self.assertEqual(thresholds.action_confidence_threshold, 0.6)

        with patch.dict(os.environ, {
            "JEV_NOUL_CANDIDATE_THRESHOLD": "0.81",
            "JEV_ROUTER_CONFIDENCE_THRESHOLD": "0.42",
            "JEV_ACTION_CONFIDENCE_THRESHOLD": "0.93",
        }, clear=True):
            thresholds = load_jev_thresholds()
        self.assertEqual(thresholds.noul_candidate_threshold, 0.81)
        self.assertEqual(thresholds.router_confidence_threshold, 0.42)
        self.assertEqual(thresholds.action_confidence_threshold, 0.93)

    def test_each_invalid_threshold_is_rejected_without_echoing_its_value(self):
        for env_name in (
            "JEV_NOUL_CANDIDATE_THRESHOLD",
            "JEV_ROUTER_CONFIDENCE_THRESHOLD",
            "JEV_ACTION_CONFIDENCE_THRESHOLD",
        ):
            with self.subTest(env_name=env_name):
                with patch.dict(os.environ, {env_name: "secret-invalid-threshold"}, clear=True):
                    with self.assertRaises(JevConfigurationError) as raised:
                        load_jev_thresholds()
                self.assertIn(env_name, str(raised.exception))
                self.assertNotIn("secret-invalid-threshold", str(raised.exception))

    def test_existing_process_environment_wins_and_missing_proxy_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "TYPESAFE_API_KEY=file-key\nHTTP_PROXY=http://file-proxy\nHTTPS_PROXY=http://file-proxy\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "TYPESAFE_API_KEY": "process-key",
                    "HTTP_PROXY": "http://process-proxy",
                    "HTTPS_PROXY": "http://process-proxy",
                },
                clear=True,
            ):
                load_typesafe_environment(env_file)
                self.assertEqual(os.environ["TYPESAFE_API_KEY"], "process-key")
                self.assertEqual(os.environ["HTTP_PROXY"], "http://process-proxy")

            key_only = Path(directory) / ".env-key-only"
            key_only.write_text("TYPESAFE_API_KEY=file-key\n", encoding="utf-8")
            with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}, clear=True):
                with self.assertRaises(JevConfigurationError) as raised:
                    load_typesafe_environment(key_only)
                self.assertNotIn("test-key", str(raised.exception))

    def test_sdk_client_uses_configured_http_proxy_even_with_inherited_socks_fallback(self):
        with patch.dict(os.environ, {
            "TYPESAFE_API_KEY": "test-key-sentinel",
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "JEV_NOUL_CANDIDATE_THRESHOLD": "0.6",
            "JEV_ROUTER_CONFIDENCE_THRESHOLD": "0.6",
            "JEV_ACTION_CONFIDENCE_THRESHOLD": "0.6",
            "ALL_PROXY": "socks5://127.0.0.1:1080",
            "all_proxy": "socks5://127.0.0.1:1080",
        }):
            load_typesafe_environment()
            with use_configured_http_proxy_fallback():
                client = TypeSafeClient(timeout=1, retry=RetryPolicy(max_retries=0))
                client.close()
            self.assertTrue(os.environ["ALL_PROXY"].startswith("socks5://"))


class CatalogDescriptionTests(unittest.TestCase):
    def test_all_plant_and_zombie_entries_have_english_descriptions(self):
        self.assertEqual(len(PLANTS), 49)
        self.assertEqual(len(ZOMBIES), 34)
        self.assertEqual(ZOMBIE_NAMES, tuple(zombie.name for zombie in ZOMBIES))
        for entry in (*PLANTS, *ZOMBIES):
            description = entry.description_en
            self.assertTrue(description.strip())
            self.assertTrue(description.isascii())

    def test_zombie_lookup_keeps_names_and_rejects_unknown_codes(self):
        self.assertEqual(zombie_info(0).name, "normal_zombie")
        self.assertEqual(zombie_name(0), "normal_zombie")
        self.assertIsNone(zombie_info(-1))
        self.assertIsNone(zombie_info(1000))


class JevClientTests(unittest.TestCase):
    def test_router_questions_are_three_nouls_and_one_next_action_choice(self):
        questions = build_router_questions()
        self.assertEqual(set(questions), {"should_collect", "should_plant", "should_shovel", "next_action"})
        self.assertEqual([questions[key].type for key in ("should_collect", "should_plant", "should_shovel")], ["noul"] * 3)
        self.assertEqual(questions["should_collect"].criteria.keys(), {"true", "false"})
        self.assertEqual(set(questions["next_action"].criteria), {"wait", "collect", "plant", "shovel"})
        self.assertIn("0.6", questions["should_plant"].instructions)
        self.assertIn("should_plant", questions["next_action"].instructions)

        configured_questions = build_router_questions(0.82)
        self.assertIn("0.82", configured_questions["should_collect"].instructions)
        self.assertIn("0.82 candidate threshold", configured_questions["next_action"].instructions)

    def test_typesafe_state_keeps_only_the_observed_zombie_ability_context(self):
        state = jev_state(zombies=[
            {"type_code": 0, "type_name": "normal_zombie", "row": 0},
            {"type_code": 0, "type_name": "normal_zombie", "row": 1},
            {"type_code": 33, "type_name": "custom_zombie", "row": 2},
            {"type_code": 999, "type_name": "unknown", "row": 3},
        ])
        # Without a branch the function returns the shared observed-zombie context
        # only, which is exactly what the Trace recorder reads (V31).
        result = build_typesafe_state(state)
        self.assertEqual(set(result), {"catalog_context"})
        context = result["catalog_context"]["zombie_abilities"]
        self.assertEqual([item["type_name"] for item in context], ["normal_zombie", "custom_zombie"])
        self.assertTrue(all(item["description_en"] for item in context))
        for leaked in ("zombies", "items", "cards", "board", "sample_sequence", "availability", "raw_snapshot"):
            self.assertNotIn(leaked, result)

    def test_collect_action_uses_current_item_index_and_same_sample_target(self):
        items = [
            {"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0},
            {"type_code": 999, "type_name": "unknown", "x": 140.0, "y": 220.0},
        ]
        questions = build_action_questions("collect", jev_state(items=items))
        self.assertEqual(set(questions.questions), {"item"})
        self.assertEqual(set(questions.option_targets["item"]), {"item_0"})
        self.assertIn("sun", questions.questions["item"].criteria["item_0"])
        self.assertEqual(
            questions.option_targets["item"]["item_0"],
            {"action": "collect_item", "type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0},
        )

    def test_plant_action_uses_english_catalog_criteria_and_empty_cells(self):
        cells = [[False for _ in range(9)] for _ in range(5)]
        cells[2][4] = None
        cards = [
            {"slot": 0, "type_code": 0, "type_name": "peashooter", "usable": True, "cooldown_ready": True},
            {"slot": 1, "type_code": 1, "type_name": "sunflower", "usable": False, "cooldown_ready": True},
        ]
        questions = build_action_questions("plant", jev_state(cards=cards, cells=cells))
        self.assertEqual(
            set(questions.questions), {"plant_type", "cell"}
        )
        self.assertEqual(set(questions.questions["plant_type"].criteria), {"peashooter"})
        self.assertEqual(
            questions.questions["plant_type"].criteria["peashooter"],
            plant_info(0).description_en,
        )
        self.assertEqual(set(questions.option_targets["cell"]), {"r2c4"})
        self.assertEqual(questions.option_targets["cell"]["r2c4"], {"row": 2, "col": 4})

    def test_shovel_action_lists_only_occupied_cells_and_their_plant_types(self):
        cells = [[False for _ in range(9)] for _ in range(5)]
        cells[1][3] = "plant:wall_nut"
        plants = [
            {"type_code": 3, "type_name": "wall_nut", "row": 1, "col": 3},
            {"type_code": 30, "type_name": "pumpkin", "row": 1, "col": 3},
        ]
        questions = build_action_questions("shovel", jev_state(cells=cells, plants=plants))
        self.assertEqual(set(questions.option_targets["cell"]), {"r1c3"})
        self.assertIn("wall nut", questions.questions["cell"].criteria["r1c3"])
        self.assertIn("pumpkin", questions.questions["cell"].criteria["r1c3"])

    def test_router_reconcile_applies_candidate_threshold_choice_confidence_and_wait(self):
        exact_boundary = router_response(collect=0.6, plant=0.8, shovel=0.59, choice="collect")
        exact_boundary.answers["next_action"] = ChoiceAnswer(
            choice="collect",
            confidence=0.75,
            probabilities={"wait": 0.1, "collect": 0.75, "plant": 0.1, "shovel": 0.05},
        )
        decision = reconcile_router(exact_boundary)
        self.assertEqual(decision.candidates, ("collect", "plant"))
        self.assertEqual(decision.effective_action, "collect")

        mismatch = router_response(choice="shovel", confidence=0.9, shovel=0.59)
        mismatch.answers["next_action"] = ChoiceAnswer(
            choice="shovel", confidence=0.9,
            probabilities={"wait": 0.05, "collect": 0.05, "plant": 0.05, "shovel": 0.85},
        )
        self.assertEqual(reconcile_router(mismatch).effective_action, "wait")

        low_confidence = router_response(choice="plant", confidence=0.59)
        low_confidence.answers["next_action"] = ChoiceAnswer(
            choice="plant", confidence=0.59,
            probabilities={"wait": 0.1, "collect": 0.1, "plant": 0.7, "shovel": 0.1},
        )
        self.assertEqual(reconcile_router(low_confidence).effective_action, "wait")

    def test_router_noul_and_choice_confidence_thresholds_are_independent(self):
        response = router_response(choice="collect", confidence=0.55, collect=0.8, plant=0.79)
        decision = reconcile_router(
            response,
            noul_candidate_threshold=0.8,
            confidence_threshold=0.5,
        )
        self.assertEqual(decision.candidates, ("collect",))
        self.assertEqual(decision.effective_action, "collect")
        self.assertEqual(decision.noul_candidate_threshold, 0.8)
        self.assertEqual(decision.confidence_threshold, 0.5)

    def test_action_answers_map_only_valid_confident_typed_choices(self):
        cell_targets = {"cell": {"r2c4": {"row": 2, "col": 4}}}
        plant_targets = {"plant_type": {"peashooter": {"type_name": "peashooter"}}, **cell_targets}
        response = choice_response({
            "plant_type": ChoiceAnswer(choice="peashooter", confidence=0.8, probabilities={"peashooter": 1.0}),
            "cell": ChoiceAnswer(choice="r2c4", confidence=0.7, probabilities={"r2c4": 1.0}),
        })
        decision = validate_action_answers(response, intent="plant", option_targets=plant_targets)
        self.assertEqual(decision.effective_action, "plant")
        self.assertEqual(decision.target, {"action": "place_plant", "type_name": "peashooter", "row": 2, "col": 4})

        lower_action_gate = choice_response({
            "plant_type": ChoiceAnswer(choice="peashooter", confidence=0.65, probabilities={"peashooter": 1.0}),
            "cell": ChoiceAnswer(choice="r2c4", confidence=0.65, probabilities={"r2c4": 1.0}),
        })
        accepted = validate_action_answers(
            lower_action_gate,
            intent="plant",
            option_targets=plant_targets,
            confidence_threshold=0.6,
        )
        rejected = validate_action_answers(
            lower_action_gate,
            intent="plant",
            option_targets=plant_targets,
            confidence_threshold=0.7,
        )
        self.assertEqual(accepted.effective_action, "plant")
        self.assertEqual(rejected.effective_action, "wait")
        self.assertEqual(accepted.confidence_threshold, 0.6)
        self.assertEqual(rejected.confidence_threshold, 0.7)

        low = choice_response({
            "plant_type": ChoiceAnswer(choice="peashooter", confidence=0.59, probabilities={"peashooter": 1.0}),
            "cell": ChoiceAnswer(choice="r2c4", confidence=0.7, probabilities={"r2c4": 1.0}),
        })
        self.assertEqual(validate_action_answers(low, intent="plant", option_targets=plant_targets).effective_action, "wait")

        malformed = choice_response({"cell": SimpleNamespace(type="noul", noul=0.9)})
        with self.assertRaises(JevDecisionError):
            validate_action_answers(malformed, intent="shovel", option_targets=cell_targets)

    def test_client_makes_router_then_one_action_request_with_same_sample(self):
        cells = [[False for _ in range(9)] for _ in range(5)]
        cells[2][4] = None
        state = jev_state(
            cards=[{"slot": 0, "type_code": 0, "type_name": "peashooter", "usable": True, "cooldown_ready": True}],
            zombies=[{"type_code": 0, "type_name": "normal_zombie", "row": 2}],
            cells=cells,
        )
        action = choice_response({
            "plant_type": ChoiceAnswer(choice="peashooter", confidence=0.9, probabilities={"peashooter": 1.0}),
            "cell": ChoiceAnswer(choice="r2c4", confidence=0.8, probabilities={"r2c4": 1.0}),
        })

        class FakeSdkClient:
            def __init__(self):
                self.calls = []
                self.responses = [router_response(), action]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def system_one(self, **kwargs):
                self.calls.append(kwargs)
                return self.responses.pop(0)

        fake = FakeSdkClient()
        with patch.dict(
            os.environ,
            {
                "TYPESAFE_API_KEY": "test-key-sentinel",
                "HTTP_PROXY": "http://127.0.0.1:7890",
                "HTTPS_PROXY": "http://127.0.0.1:7890",
                "JEV_NOUL_CANDIDATE_THRESHOLD": "0.6",
                "JEV_ROUTER_CONFIDENCE_THRESHOLD": "0.6",
                "JEV_ACTION_CONFIDENCE_THRESHOLD": "0.6",
            },
        ):
            client = JevClient(client_factory=lambda: fake)
            router = client.decide_router(state)
            selected = client.decide_action(router.effective_action, state)

        self.assertEqual(router.effective_action, "plant")
        self.assertEqual(selected.target, {"action": "place_plant", "type_name": "peashooter", "row": 2, "col": 4})
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[0]["model"], "jev-latest")
        self.assertEqual(set(fake.calls[0]["questions"]), {"should_collect", "should_plant", "should_shovel", "next_action"})
        self.assertEqual(fake.calls[0]["state"]["sample_sequence"], fake.calls[1]["state"]["sample_sequence"])
        self.assertEqual(fake.calls[0]["state"]["catalog_context"]["zombie_abilities"][0]["type_name"], "normal_zombie")
        self.assertEqual(set(fake.calls[1]["questions"]), {"plant_type", "cell"})
        self.assertIn("Fires peas", fake.calls[1]["questions"]["plant_type"].criteria["peashooter"])

    def test_client_uses_separate_noul_router_and_action_thresholds_from_environment(self):
        state = jev_state(items=[{"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0}])
        action_response = choice_response({
            "item": ChoiceAnswer(choice="item_0", confidence=0.65, probabilities={"item_0": 1.0}),
        })

        class FakeSdkClient:
            def __init__(self):
                self.calls = []
                self.responses = [
                    router_response(choice="collect", confidence=0.55, collect=0.8, plant=0.79),
                    action_response,
                ]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def system_one(self, **kwargs):
                self.calls.append(kwargs)
                return self.responses.pop(0)

        fake = FakeSdkClient()
        with patch.dict(os.environ, {
            "TYPESAFE_API_KEY": "test-key-sentinel",
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "JEV_NOUL_CANDIDATE_THRESHOLD": "0.8",
            "JEV_ROUTER_CONFIDENCE_THRESHOLD": "0.5",
            "JEV_ACTION_CONFIDENCE_THRESHOLD": "0.7",
        }):
            client = JevClient(client_factory=lambda: fake)
            router = client.decide_router(state)
            action = client.decide_action(router.effective_action, state)

        self.assertEqual(router.effective_action, "collect")
        self.assertEqual(router.noul_candidate_threshold, 0.8)
        self.assertEqual(router.confidence_threshold, 0.5)
        self.assertIn("0.8", fake.calls[0]["questions"]["should_collect"].instructions)
        self.assertEqual(action.effective_action, "wait")
        self.assertEqual(action.confidence_threshold, 0.7)
        self.assertEqual(action.fallback_reason, "item_confidence_below_threshold")

    def test_client_skips_action_request_when_no_valid_target_exists(self):
        class FakeSdkClient:
            def __init__(self):
                self.calls = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def system_one(self, **kwargs):
                self.calls.append(kwargs)
                return router_response(choice="collect", confidence=0.9, collect=0.9)

        fake = FakeSdkClient()
        with patch.dict(os.environ, {
            "TYPESAFE_API_KEY": "test-key-sentinel",
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "JEV_NOUL_CANDIDATE_THRESHOLD": "0.6",
            "JEV_ROUTER_CONFIDENCE_THRESHOLD": "0.6",
            "JEV_ACTION_CONFIDENCE_THRESHOLD": "0.6",
        }):
            client = JevClient(client_factory=lambda: fake)
            router = client.decide_router(jev_state())
            skipped = client.decide_action(router.effective_action, jev_state())
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(skipped.status, "skipped_no_targets")
        self.assertEqual(skipped.effective_action, "wait")

    def test_api_error_is_sanitized(self):
        class RaisingSdkClient:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def system_one(self, **_kwargs):
                raise RuntimeError("key=test-key-sentinel raw response body")

        with patch.dict(os.environ, {
            "TYPESAFE_API_KEY": "test-key-sentinel",
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "JEV_NOUL_CANDIDATE_THRESHOLD": "0.6",
            "JEV_ROUTER_CONFIDENCE_THRESHOLD": "0.6",
            "JEV_ACTION_CONFIDENCE_THRESHOLD": "0.6",
        }):
            with self.assertRaises(JevApiError) as raised:
                JevClient(client_factory=RaisingSdkClient).decide_router(jev_state())
        self.assertNotIn("test-key-sentinel", str(raised.exception))
        self.assertNotIn("raw response body", str(raised.exception))


class RuntimeConfigTests(unittest.TestCase):
    def test_runtime_config_freezes_thresholds_model_and_credential_presence(self):
        with patch.dict(
            os.environ,
            async_client_environment(
                JEV_NOUL_CANDIDATE_THRESHOLD="0.8",
                JEV_ROUTER_CONFIDENCE_THRESHOLD="0.5",
                JEV_ACTION_CONFIDENCE_THRESHOLD="0.7",
            ),
            clear=True,
        ):
            config = load_runtime_config()
        self.assertIsInstance(config, RuntimeConfig)
        self.assertEqual(config.thresholds.noul_candidate_threshold, 0.8)
        self.assertEqual(config.thresholds.router_confidence_threshold, 0.5)
        self.assertEqual(config.thresholds.action_confidence_threshold, 0.7)
        self.assertEqual(config.model_name, "jev-latest")
        self.assertTrue(config.api_key_present)
        self.assertTrue(config.http_proxy_present)
        self.assertTrue(config.https_proxy_present)
        self.assertNotIn("test-key-sentinel", repr(config))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.model_name = "other-model"

    def test_runtime_config_fails_closed_without_the_key_or_both_proxies(self):
        with tempfile.TemporaryDirectory() as directory:
            key_only = Path(directory) / ".env-key-only"
            key_only.write_text("TYPESAFE_API_KEY=test-key-sentinel\n", encoding="utf-8")
            with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key-sentinel"}, clear=True):
                with self.assertRaises(JevConfigurationError) as raised:
                    load_runtime_config(key_only)
        self.assertIn("HTTP_PROXY", str(raised.exception))
        self.assertNotIn("test-key-sentinel", str(raised.exception))


class AsyncJevClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_request_returns_the_typed_response_with_integer_latency(self):
        typed_response = router_response()
        fake = FakeAsyncTypeSafeClient()
        fake.responses = [typed_response]
        questions = build_router_questions()
        with patch.dict(os.environ, async_client_environment()):
            async with AsyncJevClient(client_factory=lambda: fake) as client:
                response, latency_ms = await client.system_one(state=jev_state(), questions=questions)
        self.assertIs(response, typed_response)
        self.assertIsInstance(latency_ms, int)
        self.assertGreaterEqual(latency_ms, 0)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["model"], "jev-latest")
        self.assertIs(fake.calls[0]["questions"], questions)
        self.assertEqual(fake.calls[0]["state"]["sample_sequence"], 2104)
        self.assertTrue(fake.closed)

    async def test_runtime_config_is_read_once_at_open_and_never_per_request(self):
        fake = FakeAsyncTypeSafeClient()
        with patch.dict(
            os.environ,
            async_client_environment(
                JEV_NOUL_CANDIDATE_THRESHOLD="0.8",
                JEV_ROUTER_CONFIDENCE_THRESHOLD="0.5",
                JEV_ACTION_CONFIDENCE_THRESHOLD="0.7",
            ),
        ), patch("jev.config.load_jev_thresholds", wraps=load_jev_thresholds) as threshold_reads:
            async with AsyncJevClient(client_factory=lambda: fake) as client:
                reads_at_open = threshold_reads.call_count
                self.assertEqual(reads_at_open, 1)
                self.assertEqual(client.config.thresholds.noul_candidate_threshold, 0.8)
                os.environ["JEV_NOUL_CANDIDATE_THRESHOLD"] = "0.11"
                for _ in range(3):
                    await client.system_one(state=jev_state(), questions=build_router_questions())
                self.assertEqual(threshold_reads.call_count, reads_at_open)
                self.assertEqual(client.config.thresholds.noul_candidate_threshold, 0.8)
                self.assertEqual(load_jev_thresholds().noul_candidate_threshold, 0.11)
            self.assertEqual(threshold_reads.call_count, reads_at_open)
        frozen = client.config.thresholds
        self.assertEqual(frozen.router_confidence_threshold, 0.5)
        self.assertEqual(frozen.action_confidence_threshold, 0.7)
        self.assertEqual(client.config.model_name, "jev-latest")
        self.assertEqual(len(fake.calls), 3)

    async def test_proxy_fallback_applies_once_and_restores_pre_existing_values(self):
        fake = FakeAsyncTypeSafeClient()
        configured = ("http://127.0.0.1:7890", "http://127.0.0.1:7890")
        inherited = ("socks5://127.0.0.1:1080", "socks5://127.0.0.1:1080")
        real_fallback = use_configured_http_proxy_fallback
        fallback_entries = []

        def counting_fallback():
            fallback_entries.append(True)
            return real_fallback()

        with patch.dict(
            os.environ,
            async_client_environment(ALL_PROXY=inherited[0], all_proxy=inherited[1]),
        ), patch("jev.config.use_configured_http_proxy_fallback", counting_fallback):
            inherited_before = proxy_snapshot()
            async with AsyncJevClient(client_factory=lambda: fake) as client:
                applied_inside = proxy_snapshot()
                requests = [
                    client.system_one(state=jev_state(), questions=build_router_questions()) for _ in range(4)
                ]
                results = await asyncio.gather(*requests)
                applied_during = proxy_snapshot()
            restored_after = proxy_snapshot()

        self.assertEqual(inherited_before, inherited)
        self.assertEqual(applied_inside, configured)
        self.assertEqual(applied_during, configured)
        self.assertEqual(restored_after, inherited)
        self.assertEqual(len(fallback_entries), 1)
        self.assertEqual(len(fake.calls), 4)
        self.assertEqual(len(results), 4)
        self.assertEqual(set(fake.proxy_observations), {configured})

    async def test_proxy_fallback_removes_absent_proxy_keys_after_close(self):
        fake = FakeAsyncTypeSafeClient()
        with patch.dict(os.environ, async_client_environment(), clear=True):
            self.assertEqual(proxy_snapshot(), (None, None))
            async with AsyncJevClient(client_factory=lambda: fake) as client:
                self.assertEqual(proxy_snapshot(), ("http://127.0.0.1:7890", "http://127.0.0.1:7890"))
                await client.system_one(state=jev_state(), questions=build_router_questions())
            self.assertEqual(proxy_snapshot(), (None, None))
            self.assertNotIn("ALL_PROXY", os.environ)
            self.assertNotIn("all_proxy", os.environ)

    async def test_global_in_flight_peak_is_two_for_five_concurrent_requests(self):
        gated = GatedAsyncTypeSafeClient()
        with patch.dict(os.environ, async_client_environment()):
            async with AsyncJevClient(client_factory=lambda: gated) as client:
                tasks = [
                    asyncio.create_task(
                        client.system_one(state=jev_state(), questions=build_router_questions())
                    )
                    for _ in range(5)
                ]
                await asyncio.wait_for(gated.limit_reached.wait(), timeout=5)
                self.assertEqual(gated.in_flight, GLOBAL_IN_FLIGHT_LIMIT)
                self.assertEqual(gated.peak_in_flight, GLOBAL_IN_FLIGHT_LIMIT)
                self.assertEqual(len(gated.calls), 0)
                gated.release.set()
                results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
        self.assertEqual(gated.peak_in_flight, GLOBAL_IN_FLIGHT_LIMIT)
        self.assertEqual(gated.in_flight, 0)
        self.assertEqual(len(gated.calls), 5)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(isinstance(latency_ms, int) for _response, latency_ms in results))
        self.assertTrue(gated.closed)

    async def test_async_request_errors_stay_sanitized(self):
        class RaisingAsyncTypeSafeClient:
            async def system_one(self, **_kwargs):
                raise RuntimeError(
                    "key=test-key-sentinel Authorization: Bearer sentinel-token raw response body"
                )

            async def aclose(self):
                pass

        with patch.dict(os.environ, async_client_environment()):
            async with AsyncJevClient(client_factory=RaisingAsyncTypeSafeClient) as client:
                with self.assertRaises(JevApiError) as raised:
                    await client.system_one(state=jev_state(), questions=build_router_questions())
        message = str(raised.exception)
        self.assertEqual(raised.exception.exception_type, "RuntimeError")
        self.assertIn("RuntimeError", message)
        self.assertIsNone(raised.exception.__cause__)
        for leaked in ("test-key-sentinel", "Bearer", "sentinel-token", "raw response body"):
            self.assertNotIn(leaked, message)

    async def test_requests_and_nested_lifecycles_are_rejected_before_open(self):
        fake = FakeAsyncTypeSafeClient()
        client = AsyncJevClient(client_factory=lambda: fake)
        with self.assertRaises(RuntimeError):
            await client.system_one(state=jev_state(), questions=build_router_questions())
        with self.assertRaises(RuntimeError):
            _ = client.config
        with patch.dict(os.environ, async_client_environment()):
            async with client:
                with self.assertRaises(RuntimeError):
                    async with client:
                        pass
        self.assertEqual(len(fake.calls), 0)
        self.assertTrue(fake.closed)


class BranchFanOutTests(unittest.IsolatedAsyncioTestCase):
    """T4 checks: one atomic fan-out request per branch decision (V29–V33, V40)."""

    def plant_state(self, *, sun=500, cards=PLANT_CARDS, cells=None, zombies=None):
        return jev_state(
            cards=list(cards),
            cells=cells if cells is not None else empty_cells(),
            zombies=zombies or [],
        )

    async def decide_plant(self, state, *, response, thresholds=None):
        fake = FakeAsyncTypeSafeClient()
        fake.responses = [response]
        environment = async_client_environment(**{k: str(v) for k, v in (thresholds or {}).items()})
        with patch.dict(os.environ, environment, clear=True):
            async with AsyncJevClient(client_factory=lambda: fake) as client:
                decision = await client.decide_plant(state)
        return decision, fake

    # ------------------------------------------------------------ V29 topology

    async def test_one_plant_decision_issues_exactly_one_fan_out_request(self):
        state = self.plant_state()
        question_set = build_plant_questions(state)
        decision, fake = await self.decide_plant(
            state, response=plant_answer(question_set.questions)
        )
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(set(fake.calls[0]["questions"]), set(question_set.questions))
        self.assertEqual(
            set(fake.calls[0]["questions"]),
            {PLANT_TARGET_QUESTION_ID},
        )
        self.assertEqual(decision.status, "selected")

    async def test_one_collect_decision_issues_exactly_one_fan_out_request(self):
        items = [{"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0}]
        state, source = jev_state(items=items), all_state(items=items)
        question_set = build_collect_questions(state, all_state=source)
        fake = FakeAsyncTypeSafeClient()
        fake.responses = [collect_answer(question_set.questions)]
        with patch.dict(os.environ, async_client_environment(), clear=True):
            async with AsyncJevClient(client_factory=lambda: fake) as client:
                decision = await client.decide_collect(state, all_state=source)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(
            set(fake.calls[0]["questions"]), {COLLECT_NOW_QUESTION_ID}
        )
        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.target["action"], "collect_item")

    # --------------------------------------------------- V43 bound item identity

    async def test_every_collect_option_binds_the_same_sample_item_id(self):
        items = [{"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0}, {"type_code": 4, "type_name": "sun", "x": 160.0, "y": 220.0}]
        question_set = build_collect_questions(jev_state(items=items), all_state=all_state(items=items))
        self.assertEqual(question_set.choice_levels, ())
        self.assertEqual([x["item_id"] for x in question_set.candidates], [500, 501])
        self.assertEqual(set(question_set.questions), {COLLECT_NOW_QUESTION_ID})

    def test_an_item_without_a_resolvable_id_is_not_offered(self):
        items = [{"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0}]
        source = all_state(items=items)
        source["items"][0]["id"] = None
        question_set = build_collect_questions(jev_state(items=items), all_state=source)
        self.assertEqual(question_set.candidates, ())
        self.assertEqual(question_set.choice_levels, ())

    def test_an_item_whose_all_state_record_disagrees_is_not_offered(self):
        items = [{"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0}]
        source = all_state(items=items)
        source["items"][0]["type_name"] = "wall_nut"
        question_set = build_collect_questions(jev_state(items=items), all_state=source)
        self.assertEqual(question_set.questions, {})
        self.assertEqual(question_set.candidates, ())

    def test_without_an_all_state_no_option_can_be_bound(self):
        # Fail closed: asking about a target that could never be verified at dispatch
        # would only burn a request.
        question_set = build_collect_questions(
            jev_state(items=[{"type_code": 4, "type_name": "sun", "x": 1.0, "y": 2.0}])
        )
        self.assertEqual(question_set.questions, {})
        self.assertEqual(question_set.candidates, ())

    async def test_neither_the_state_nor_the_option_text_carries_the_bound_id(self):
        items = [{"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0}]
        state, source = jev_state(items=items), all_state(items=items)
        question_set = build_collect_questions(state, all_state=source)
        fake = FakeAsyncTypeSafeClient()
        fake.responses = [collect_answer(question_set.questions)]
        with patch.dict(os.environ, async_client_environment(), clear=True):
            async with AsyncJevClient(client_factory=lambda: fake) as client:
                decision = await client.decide_collect(state, all_state=source)

        sent = fake.calls[0]["state"]
        self.assertEqual(sent["items"], [{"type_code": 4, "type_name": "sun", "count": 1}])
        for banned in ("id", "item_id", "item_index", "x", "y"):
            self.assertNotIn(banned, sent["items"][0])
        criteria = fake.calls[0]["questions"][COLLECT_NOW_QUESTION_ID].criteria
        self.assertNotIn("500", " ".join(str(value) for value in criteria.values()))
        self.assertEqual(decision.target["item_id"], 500)

    # ------------------------------------------------------------ V30 atomicity

    async def test_every_question_judges_one_attribute_and_merge_is_unit_testable(self):
        questions = build_plant_questions(self.plant_state()).questions
        self.assertEqual(set(questions), {PLANT_TARGET_QUESTION_ID})
        self.assertEqual([x.kind for x in PLANT_QUESTION_SPECS], ["choice"])
        question_set = build_plant_questions(self.plant_state())
        decision = combine_plant_decision(
            plant_answer(questions, choice=DISCARD_OPTION_ID), question_set=question_set
        )
        self.assertEqual(decision.status, "model_wait")
        self.assertIsNone(decision.target)

    async def test_plant_request_state_carries_only_the_question_fields(self):
        state = self.plant_state()
        questions = build_plant_questions(state).questions
        _, fake = await self.decide_plant(state, response=plant_answer(questions))
        sent = fake.calls[0]["state"]
        self.assertEqual(set(sent), set(PLANT_STATE_FIELDS) | {"current_intent", "last_actual_result"})
        for banned in ("sample_sequence", "availability", "source", "phase", "rows", "economy_signal", "raw_snapshot"):
            self.assertNotIn(banned, sent)
        self.assertEqual(sent["sun"], state["sun_balance"])
        self.assertEqual(len(sent["cards"]), len(PLANT_CARDS))

    async def test_the_plant_request_state_carries_lane_role_and_column_facts(self):
        """V64/OD-49/OD-50: the shared input carries layout, role and direction facts."""
        state = self.plant_state()
        questions = build_plant_questions(state).questions
        _, fake = await self.decide_plant(state, response=plant_answer(questions))
        sent = fake.calls[0]["state"]
        self.assertEqual(
            sent["lane_composition"],
            [{"row": row, "resource": 0, "attacker": 0, "defender": 0} for row in range(5)],
        )
        direction = sent["board"]["column_direction"]
        self.assertEqual(direction["house_side_col"], 0)
        self.assertEqual(direction["zombie_side_col"], state["board"]["cols"] - 1)
        self.assertTrue(direction["increasing_col_moves_toward_zombies"])
        self.assertIn("first_cell_center", direction["geometry"])
        self.assertIn("horizontal_spacing", direction["geometry"])
        self.assertEqual(
            {card_["type_name"]: card_["role"] for card_ in sent["cards"]},
            {"peashooter": "attacker", "sunflower": "resource", "wall_nut": "defender"},
        )
        # Facts and semantics only: no recommendation, quota, or layout answer.
        for banned in ("recommend", "quota", "ideal", "priority", "urgency", "phase", "advice"):
            self.assertNotIn(banned, json.dumps(sent))

    async def test_collect_request_state_carries_only_the_items(self):
        items = [
            {"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0},
            {"type_code": 999, "type_name": "unknown", "x": 140.0, "y": 220.0},
        ]
        state, source = jev_state(items=items), all_state(items=items)
        question_set = build_collect_questions(state, all_state=source)
        fake = FakeAsyncTypeSafeClient()
        fake.responses = [collect_answer(question_set.questions)]
        with patch.dict(os.environ, async_client_environment(), clear=True):
            async with AsyncJevClient(client_factory=lambda: fake) as client:
                await client.decide_collect(state, all_state=source)
        sent = fake.calls[0]["state"]
        self.assertEqual(set(sent), set(COLLECT_STATE_FIELDS))
        self.assertEqual(sent["items"], [{"type_code": 4, "type_name": "sun", "count": 1}])
        self.assertIn("catalog_context", sent)

    async def test_no_question_asks_the_model_to_count_or_to_calculate(self):
        banned = (
            "sum of",
            "total number",
            "how many",
            "count the",
            "calculate",
            "average",
            "percentage",
            "multiply",
            "divide",
            "plus",
            "minus",
        )
        state = self.plant_state(zombies=[{"type_code": 0, "type_name": "normal_zombie", "row": 1, "hp": 270, "distance_to_house_cells": 3}])
        question_sets = (
            build_plant_questions(state),
            build_collect_questions(jev_state(items=[{"type_code": 4, "type_name": "sun", "x": 1.0, "y": 2.0}])),
        )
        for question_set in question_sets:
            for question_id, question in question_set.questions.items():
                text = json.dumps(question.model_dump(exclude_none=True)).lower()
                for token in banned:
                    self.assertNotIn(token, text, f"{question_id} asks for arithmetic: {token}")

    # --------------------------------------------------- V32 candidates/re-rank

    async def test_candidates_are_complete_validated_and_never_truncated(self):
        state = self.plant_state()
        question_set = build_plant_questions(state)
        criteria = question_set.questions[PLANT_TARGET_QUESTION_ID].criteria
        self.assertEqual(len(criteria), 3 * 45 + 1)
        self.assertIn(DISCARD_OPTION_ID, criteria)
        affordable = {card["type_name"] for card in PLANT_CARDS}
        offered = {key for key in criteria if key != DISCARD_OPTION_ID}
        expected = {f"{name}@r{row}c{col}" for name in affordable for row in range(5) for col in range(9)}
        self.assertEqual(offered, expected)
        self.assertEqual(len(question_set.candidates), 3 * 45)
        for candidate in question_set.candidates:
            self.assertIn(candidate["type_name"], affordable)
            self.assertEqual(state["board"]["cells"][candidate["row"]][candidate["col"]], None)
        self.assertTrue(
            criteria[plant_option_id("peashooter", 2, 4)]["plant_ability"].startswith("Fires peas")
        )
        # V75: the option also states how the plant reaches zombies, so placement
        # never depends on inferring ranged/melee from the prose.
        self.assertEqual(criteria[plant_option_id("peashooter", 2, 4)]["engagement"], "ranged")

    async def test_choice_is_preserved_without_lane_reranking(self):
        state = self.plant_state()
        questions = build_plant_questions(state).questions
        chosen = plant_option_id("peashooter", 2, 4)
        response = plant_answer(questions, choice=chosen, confidence=0.05,
            weights={chosen: 0.5, plant_option_id("wall_nut", 0, 7): 0.3})
        decision, _ = await self.decide_plant(state, response=response)
        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.target, {"action": "place_plant", "type_name": "peashooter", "row": 2, "col": 4})
        self.assertFalse(decision.answers["merge"]["reranked"])

    async def test_without_a_plantable_candidate_no_request_is_sent_and_it_waits(self):
        state = jev_state(cards=list(PLANT_CARDS), cells=[[False] * 9 for _ in range(5)])
        question_set = build_plant_questions(state)
        self.assertEqual(question_set.questions, {})
        decision, fake = await self.decide_plant(state, response=plant_answer({}))
        self.assertEqual(fake.calls, [])
        self.assertEqual(decision.status, "skipped_no_targets")
        self.assertEqual(decision.effective_action, "wait")
        self.assertIsNone(decision.target)

    async def test_choice_may_select_the_discard_option_and_then_waits(self):
        state = self.plant_state()
        question_set = build_plant_questions(state)
        response = plant_answer(question_set.questions, choice=DISCARD_OPTION_ID)
        decision, fake = await self.decide_plant(state, response=response)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(decision.status, "model_wait")
        self.assertEqual(decision.fallback_reason, "model_selected_the_discard_option")

    # -------------------------------------------------- V33 Noul gate / argmax

    async def test_a_low_confidence_target_choice_is_still_selected(self):
        state = self.plant_state(zombies=[{"type_code": 0, "type_name": "normal_zombie", "row": 0, "hp": 270, "distance_to_house_cells": 3}])
        question_set = build_plant_questions(state)
        response = plant_answer(
            question_set.questions,
            choice=plant_option_id("peashooter", 0, 4),
            confidence=0.05,
        )
        # A deliberately impossible P02 Action threshold proves it is not read.
        decision, fake = await self.decide_plant(
            state, response=response, thresholds={"JEV_ACTION_CONFIDENCE_THRESHOLD": 0.99}
        )
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.effective_action, "plant")
        self.assertEqual(
            decision.target, {"action": "place_plant", "type_name": "peashooter", "row": 0, "col": 4}
        )
        self.assertFalse(decision.answers["merge"]["reranked"])
        self.assertEqual(decision.answers["merge"]["confidence"], 0.05)
        self.assertEqual(decision.answers["merge"]["target_choice_rule"], "argmax")

    async def test_a_low_confidence_collect_target_is_still_selected(self):
        items = [{"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0}]
        state, source = jev_state(items=items), all_state(items=items)
        questions = build_collect_questions(state, all_state=source).questions
        fake = FakeAsyncTypeSafeClient()
        fake.responses = [collect_answer(questions, confidence=0.01)]
        with patch.dict(os.environ, async_client_environment(JEV_ACTION_CONFIDENCE_THRESHOLD="0.99"), clear=True):
            async with AsyncJevClient(client_factory=lambda: fake) as client:
                decision = await client.decide_collect(state, all_state=source)
        self.assertEqual(decision.status, "selected")
        self.assertEqual(len(decision.cohort), 1)
        self.assertEqual(set(fake.calls[0]["questions"]), {COLLECT_NOW_QUESTION_ID})

    # ------------------------------------------------ V58 pinned 0.5 anchor

    def test_collect_gate_is_the_reviewable_half_anchor(self):
        self.assertEqual(COLLECT_ACT_THRESHOLD, 0.5)
        items = [{"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0}]
        question_set = build_collect_questions(jev_state(items=items), all_state=all_state(items=items))
        below = combine_collect_decision(
            collect_answer(question_set.questions, should_collect=0.12), question_set=question_set
        )
        above = combine_collect_decision(
            collect_answer(question_set.questions, should_collect=0.55), question_set=question_set
        )
        self.assertEqual(below.status, "model_wait")
        self.assertEqual(below.cohort, ())
        self.assertEqual(above.status, "selected")
        self.assertEqual(len(above.cohort), 1)
        self.assertEqual(above.answers["merge"]["noul_candidate_threshold"], COLLECT_ACT_THRESHOLD)
        self.assertEqual(above.answers["merge"]["should_collect_probability"], 0.55)

    async def test_collect_conclusion_is_independent_of_the_p02_threshold(self):
        items = [{"type_code": 4, "type_name": "sun", "x": 120.0, "y": 220.0}]
        state, source = jev_state(items=items), all_state(items=items)
        questions = build_collect_questions(state, all_state=source).questions
        for env_value in ("0.3", "0.9"):
            for should_collect, expected in ((0.12, "model_wait"), (0.55, "selected")):
                fake = FakeAsyncTypeSafeClient()
                fake.responses = [collect_answer(questions, should_collect=should_collect)]
                environment = async_client_environment(JEV_NOUL_CANDIDATE_THRESHOLD=env_value)
                with self.subTest(env=env_value, should_collect=should_collect):
                    with patch.dict(os.environ, environment, clear=True):
                        async with AsyncJevClient(client_factory=lambda: fake) as client:
                            decision = await client.decide_collect(state, all_state=source)
                    self.assertEqual(decision.status, expected)
                    self.assertEqual(len(decision.cohort), 1 if expected == "selected" else 0)

    async def test_the_model_choice_alone_decides_whether_to_act(self):
        """V57/OD-41: there is no absolute plant gate; the model's own target wins.

        The distribution mirrors the real cold-start trace (best 0.36, discard
        0.13) while every removed absolute gate sat near 0.2.
        """
        state = self.plant_state()
        question_set = build_plant_questions(state)
        chosen = plant_option_id("peashooter", 0, 4)
        response = plant_answer(
            question_set.questions,
            choice=chosen,
            confidence=0.36,
            weights={chosen: 0.36, DISCARD_OPTION_ID: 0.13},
        )
        decision, fake = await self.decide_plant(state, response=response)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.target["type_name"], "peashooter")
        merge = decision.answers["merge"]
        self.assertEqual(merge["best_option"], chosen)
        self.assertEqual(merge["best_probability"], 0.36)
        self.assertEqual(merge["discard_probability"], 0.13)
        self.assertAlmostEqual(merge["margin"], 0.23, places=6)
        self.assertNotIn(
            "noul_candidate_threshold", inspect.signature(combine_plant_decision).parameters
        )

    async def test_a_tie_between_the_best_placement_and_discard_waits(self):
        """V57/OD-41: the gate is strict ``best > none``; a flat tie waits.

        90 candidates with ``best == discard == 0.5`` (margin 0) used to dispatch
        because the chosen option was not ``none_of_the_above``; the stricter rule
        makes it wait.
        """
        state = self.plant_state(cards=(plant_card(1, "sunflower", 50, slot=1), plant_card(3, "wall_nut", 50, slot=2)))
        question_set = build_plant_questions(state)
        self.assertEqual(len(question_set.candidates), 90)
        chosen = plant_option_id("wall_nut", 0, 7)
        response = plant_answer(
            question_set.questions, weights={chosen: 0.5, DISCARD_OPTION_ID: 0.5}
        )
        decision, fake = await self.decide_plant(state, response=response)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(decision.status, "model_wait")
        self.assertEqual(decision.effective_action, "wait")
        self.assertIsNone(decision.target)
        self.assertEqual(decision.fallback_reason, "discard_option_tied_or_won")
        merge = decision.answers["merge"]
        self.assertEqual(merge["chosen_option"], chosen)
        self.assertEqual(merge["best_probability"], 0.5)
        self.assertEqual(merge["discard_probability"], 0.5)
        self.assertEqual(merge["margin"], 0.0)

    async def test_a_low_confidence_discard_choice_still_waits(self):
        state = self.plant_state()
        question_set = build_plant_questions(state)
        idle = plant_answer(question_set.questions, choice=DISCARD_OPTION_ID, confidence=0.12)
        decision, fake = await self.decide_plant(state, response=idle)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(decision.status, "model_wait")
        self.assertEqual(decision.fallback_reason, "model_selected_the_discard_option")
        self.assertIsNone(decision.target)
        self.assertEqual(decision.answers["merge"]["best_option"], DISCARD_OPTION_ID)

    async def test_the_discard_option_waits_regardless_of_its_confidence(self):
        state = self.plant_state()
        question_set = build_plant_questions(state)
        response = plant_answer(
            question_set.questions,
            confidence=0.99,
            weights={DISCARD_OPTION_ID: 0.5},
        )
        decision, fake = await self.decide_plant(state, response=response)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(decision.status, "model_wait")
        self.assertEqual(decision.fallback_reason, "model_selected_the_discard_option")
        self.assertIsNone(decision.target)
        self.assertEqual(decision.answers["merge"]["chosen_option"], DISCARD_OPTION_ID)
        self.assertEqual(decision.answers["merge"]["best_option"], DISCARD_OPTION_ID)

    async def test_neither_target_merge_accepts_a_confidence_threshold(self):
        self.assertEqual(
            [spec.threshold for spec in PLANT_QUESTION_SPECS if spec.kind == "choice"], ["argmax"]
        )
        self.assertEqual(
            [spec.threshold for spec in COLLECT_QUESTION_SPECS if spec.kind == "choice"], []
        )
        state = self.plant_state()
        question_set = build_plant_questions(state)
        response = plant_answer(question_set.questions)
        for merge in (combine_plant_decision, combine_collect_decision):
            with self.subTest(merge=merge.__name__):
                self.assertNotIn("action_confidence_threshold", inspect.signature(merge).parameters)
                self.assertNotIn("noul_candidate_threshold", inspect.signature(merge).parameters)
                with self.assertRaises(TypeError):
                    merge(response, question_set=question_set, action_confidence_threshold=0.6)

    # ------------------------------------------------- V40 over-the-cap chain

    async def test_over_the_option_cap_chains_levels_without_truncating(self):
        state = self.plant_state()
        question_set = build_plant_questions(state)
        self.assertFalse(question_set.split)
        self.assertLessEqual(len(question_set.questions[PLANT_TARGET_QUESTION_ID].criteria), MAX_CHOICE_OPTIONS)

        state = self.plant_state(cards=[*PLANT_CARDS, *PLANT_CARDS_BEYOND_THE_CAP])
        big = build_plant_questions(state)
        self.assertTrue(big.split)
        self.assertEqual(len(big.candidates), 6 * 45)
        levels = {level.question_id: level for level in big.choice_levels}
        self.assertEqual(len(levels[PLANT_LANE_QUESTION_ID].targets), 5 + 1)
        self.assertLessEqual(len(levels[PLANT_LANE_QUESTION_ID].targets), MAX_CHOICE_OPTIONS)
        covered = 0
        for row in range(5):
            question_id = f"{PLANT_LANE_TARGET_QUESTION_PREFIX}{row}"
            self.assertLessEqual(len(big.questions[question_id].criteria), MAX_CHOICE_OPTIONS)
            covered += len(levels[question_id].targets) - 1
        self.assertEqual(covered, len(big.candidates))

        response = plant_answer(big.questions, lane="lane_2")
        decision, fake = await self.decide_plant(state, response=response)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.target["row"], 2)
        self.assertEqual(decision.target["action"], "place_plant")


class AsyncJevClientDefaultTransportTests(unittest.TestCase):
    def test_default_transport_opens_the_official_async_sdk_client(self):
        created = []

        def recording_factory(**kwargs):
            created.append(kwargs)
            return AsyncTypeSafeClient(**kwargs)

        async def open_and_close():
            async with AsyncJevClient():
                self.assertEqual(len(created), 1)

        with patch.dict(os.environ, async_client_environment()), patch(
            "jev.client.AsyncTypeSafeClient", recording_factory
        ):
            asyncio.run(open_and_close())
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["timeout"], REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(
            created[0]["retry"], RetryPolicy(max_retries=0, timeout=REQUEST_TIMEOUT_SECONDS)
        )


if __name__ == "__main__":
    unittest.main()


class AutonomousManagementRevisionTests(unittest.TestCase):
    def test_collect_single_gate_and_local_cohort(self):
        state = {"items": [{"type_code": 4, "type_name": "sun", "x": 120, "y": 200}, {"type_code": 4, "type_name": "sun", "x": 120, "y": 200}]}
        source = {"items": [{**item, "id": 100 + index} for index, item in enumerate(state["items"])]}
        qs = build_collect_questions(state, all_state=source)
        self.assertEqual(set(qs.questions), {COLLECT_NOW_QUESTION_ID})
        self.assertEqual(qs.choice_levels, ())
        response = SimpleNamespace(answers={COLLECT_NOW_QUESTION_ID: NoulAnswer(noul=0.9)}, model="fake", usage=None)
        result = combine_collect_decision(response, question_set=qs)
        self.assertEqual([item["item_id"] for item in result.cohort], [100, 101])
        self.assertNotIn("x", result.target)

    def test_model_input_is_fact_only_without_item_identity(self):
        state = {"items": [{"type_code": 4, "type_name": "sun", "x": 120, "y": 200, "id": 123456}], "sun_balance": 25, "cards": [plant_card(1, "sunflower", 50)], "plants": [], "zombies": [], "board": {"cells": [[None] * 9 for _ in range(5)]}}
        actual = build_typesafe_state(state, branch="collect")
        self.assertEqual(actual["items"], [{"type_code": 4, "type_name": "sun", "count": 1}])
        self.assertEqual(actual["cards"][0]["shortfall"], 25)
        for banned in ("phase", "economy_signal", "source", "raw_snapshot", "goal_profile"):
            self.assertNotIn(banned, actual)

    def test_empty_items_omit_the_collect_sub_question(self):
        from jev.questions import management_questions
        qs = build_collect_questions({"items": []}, all_state={"items": []})
        # V59/OD-44: no collectable item means no collect sub-question at all.
        self.assertEqual(qs.questions, {})
        management = management_questions(({"type_name": "sunflower", "cost": 50, "payable": True,
                                          "shortfall": 0, "usable": True, "cooldown_ready": True,
                                          "description_en": "Produces sun periodically to fund more plants.",
                                          "role": "resource"},))
        self.assertEqual(set(management), {"construction_intent", "next_construction_type"})
        self.assertEqual(len(management), 2)
        # The construction-type option must state the card's own ability text.
        self.assertIn(
            "Produces sun periodically to fund more plants.",
            management["next_construction_type"].criteria["sunflower"],
        )


class SharedIndependentAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, *, invalid=None, items=True):
        class OfflineClient(AsyncJevClient):
            @property
            def config(self): return SimpleNamespace(thresholds=SimpleNamespace(noul_candidate_threshold=0.6))
            async def system_one(self, *, state, questions, **kwargs):
                self.calls = getattr(self, "calls", []) + [(state, questions)]
                answers = {}
                for qid, question in questions.items():
                    if isinstance(question, __import__('typesafe_sdk').Noul): answers[qid] = NoulAnswer(noul=0.9)
                    else: answers[qid] = choice_for_question(question, choice="replace" if qid == "construction_intent" else "sunflower")
                if invalid: answers.pop(invalid, None)
                return SimpleNamespace(answers=answers, model="offline", usage=None), 1
        state = jev_state(cards=[plant_card(1, "sunflower", 50)], plants=[], items=[{"type_code": 4, "type_name": "sun", "x": 120, "y": 200}] if items else [])
        client = OfflineClient()
        result = await client.decide_shared(state, all_state=all_state(items=state["items"]))
        self.last_client = client
        self.assertEqual(len(client.calls), 1)
        self.assertNotIn(COLLECT_TARGET_QUESTION_ID, client.calls[0][1])
        return result

    async def test_a_cancel_intent_needs_no_construction_type_answer(self):
        # A model that cancels states no type; requiring one used to reject the whole
        # management answer and silently keep the old intent (five live occurrences).
        class OfflineCancelClient(AsyncJevClient):
            @property
            def config(self): return SimpleNamespace(thresholds=SimpleNamespace(noul_candidate_threshold=0.6))

            async def system_one(self, *, state, questions, **kwargs):
                answers = {}
                for qid, question in questions.items():
                    if isinstance(question, __import__('typesafe_sdk').Noul):
                        answers[qid] = NoulAnswer(noul=0.9)
                    elif qid == "construction_intent":
                        answers[qid] = choice_for_question(question, choice="cancel")
                    elif qid == "next_construction_type":
                        continue
                    else:
                        answers[qid] = choice_for_question(question, choice="sunflower")
                return SimpleNamespace(answers=answers, model="offline", usage=None), 1

        state = jev_state(cards=[plant_card(1, "sunflower", 50)], plants=[],
                          items=[{"type_code": 4, "type_name": "sun", "x": 120, "y": 200}])
        client = OfflineCancelClient()
        result = await client.decide_shared(state, all_state=all_state(items=state["items"]))

        self.assertNotIn("invalid_management_response", result.component_errors)
        self.assertEqual(result.management, {"operation": "cancel", "type_name": None})
        self.assertEqual(result.status, "selected")
        self.assertEqual(len(result.cohort), 1)

    async def test_management_invalid_does_not_revoke_collect(self):
        result = await self.request(invalid="construction_intent")
        self.assertEqual(result.status, "selected")
        self.assertEqual(len(result.cohort), 1)
        self.assertIsNone(result.management)
        self.assertIn("invalid_management_response", result.component_errors)

    async def test_collect_invalid_does_not_revoke_management(self):
        result = await self.request(invalid=COLLECT_NOW_QUESTION_ID)
        self.assertEqual(result.cohort, ())
        self.assertEqual(result.management["type_name"], "sunflower")
        self.assertIn("invalid_collect_response", result.component_errors)

    async def test_zero_items_still_returns_typed_intent(self):
        result = await self.request(items=False)
        self.assertEqual(result.cohort, ())
        self.assertEqual(result.management["operation"], "replace")

    async def test_zero_items_request_carries_only_management_questions(self):
        """V59/OD-44: no collectable item means no collect sub-question, but
        the management questions still travel in the one shared request."""
        result = await self.request(items=False)
        asked = set(self.last_client.calls[0][1])
        self.assertEqual(asked, {"construction_intent", "next_construction_type"})
        self.assertNotIn(COLLECT_NOW_QUESTION_ID, asked)
        self.assertNotIn("invalid_collect_response", result.component_errors)
        self.assertEqual(result.status, "model_wait")
        self.assertEqual(result.management["operation"], "replace")
        self.assertEqual(result.management["type_name"], "sunflower")


class RequestFieldAcceptanceTests(unittest.TestCase):
    def test_all_current_plant_questions_reference_supplied_observations(self):
        import re
        state = jev_state(cards=[plant_card(1, "sunflower", 50)], plants=[])
        actual = build_typesafe_state(state, branch="plant")
        for question in build_plant_questions(state).questions.values():
            for field in re.findall(r"state\.([a-z_]+)", question.instructions):
                self.assertIn(field, actual)
        self.assertEqual(len(actual["observed_lanes"]), 5)
        self.assertTrue(all("urgency" not in row for row in actual["observed_lanes"]))


class PlantExperienceLoaderTests(unittest.TestCase):
    """V72/OD-58: the hand-editable experience file loader semantics."""

    def test_loader_ignores_comments_and_blanks_keeps_order_and_strips_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experience.txt"
            path.write_text(
                "# header comment\n"
                "\n"
                "   \n"
                "  first guidance  \n"
                "# an inline comment line\n"
                "second guidance\n"
                "\tthird guidance\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_plant_experience(path),
                ("first guidance", "second guidance", "third guidance"),
            )

    def test_loader_returns_utf8_content_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experience.txt"
            path.write_text(
                "资源植物通常更安全地靠近房屋一侧。\n"
                "A durable blocker belongs toward the zombie side.\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_plant_experience(path),
                (
                    "资源植物通常更安全地靠近房屋一侧。",
                    "A durable blocker belongs toward the zombie side.",
                ),
            )

    def test_missing_file_yields_no_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_plant_experience(Path(directory) / "absent.txt"), ())

    def test_every_call_rereads_the_file_without_caching(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experience.txt"
            path.write_text("original guidance\n", encoding="utf-8")
            first = load_plant_experience(path)
            path.write_text("edited guidance\n", encoding="utf-8")
            second = load_plant_experience(path)
            self.assertEqual(first, ("original guidance",))
            self.assertEqual(second, ("edited guidance",))


class BundledPlantExperienceTests(unittest.TestCase):
    """V72/R47: the in-repo experience file stays within budget and is legal."""

    def test_bundled_file_is_present_and_matches_the_default_path(self):
        self.assertTrue(PLANT_EXPERIENCE_PATH.is_file())
        self.assertEqual(load_plant_experience(PLANT_EXPERIENCE_PATH), load_plant_experience())

    def test_bundled_file_budget_and_state_references(self):
        import re
        guidance = load_plant_experience()
        self.assertTrue(guidance)
        self.assertLessEqual(len(guidance), 12)
        self.assertLessEqual(sum(len(line) for line in guidance), 800)
        actual = build_typesafe_state(
            jev_state(cards=[plant_card(1, "sunflower", 50)], plants=[]), branch="plant"
        )
        for line in guidance:
            for field in re.findall(r"state\.([a-z_]+)", line):
                self.assertIn(field, actual)


class PlantAbilityFactsTests(unittest.TestCase):
    """V74/R49: the shared state names what this sample's plants can do."""

    def test_only_present_types_are_listed_deduplicated_and_sorted_by_name(self):
        state = jev_state(
            cards=[
                plant_card(plant_type_code("sunflower"), "sunflower", 50, slot=0),
                plant_card(plant_type_code("sunflower"), "sunflower", 50, slot=1),
                plant_card(plant_type_code("wall_nut"), "wall_nut", 50, slot=2),
            ],
            plants=[
                {"type_code": plant_type_code("peashooter"), "type_name": "peashooter", "row": 0, "col": 0, "hp": 300},
                {"type_code": plant_type_code("sunflower"), "type_name": "sunflower", "row": 1, "col": 0, "hp": 300},
            ],
        )
        abilities = build_typesafe_state(state)["catalog_context"]["plant_abilities"]
        self.assertEqual([item["type_name"] for item in abilities], ["peashooter", "sunflower", "wall_nut"])
        for item in abilities:
            info = plant_info(plant_type_code(item["type_name"]))
            self.assertEqual(set(item), {"type_name", "description_en", "role"})
            self.assertEqual(item["description_en"], info.description_en)
            self.assertEqual(item["role"], info.role)

    def test_absent_unresolved_and_descriptionless_types_are_not_invented(self):
        state = jev_state(
            cards=[
                # A code that resolves to another catalog name is not this type.
                plant_card(plant_type_code("cherry_bomb"), "sunflower", 50, slot=0),
                plant_card(999, "unknown", 50, slot=1),
            ],
            plants=[{"type_code": 999, "type_name": "unknown", "row": 0, "col": 0, "hp": 300}],
        )
        self.assertEqual(build_typesafe_state(state)["catalog_context"]["plant_abilities"], [])

    def test_a_present_type_without_a_catalog_description_is_not_described(self):
        state = jev_state(cards=[plant_card(plant_type_code("sunflower"), "sunflower", 50)])
        with patch.object(client, "plant_info", return_value=PlantInfo("sunflower", 50, "", "resource")):
            abilities = build_typesafe_state(state)["catalog_context"]["plant_abilities"]
        self.assertEqual(abilities, [])

    def test_every_plant_entity_fact_carries_a_role_without_adding_a_state_key(self):
        state = jev_state(
            cards=[plant_card(plant_type_code("sunflower"), "sunflower", 50)],
            plants=[
                {"type_code": plant_type_code("sunflower"), "type_name": "sunflower", "row": 0, "col": 0, "hp": 300},
                {"type_code": 999, "type_name": "unknown", "row": 1, "col": 0, "hp": 300},
            ],
        )
        actual = build_typesafe_state(state, branch="plant")
        self.assertEqual(set(actual), set(PLANT_STATE_FIELDS))
        self.assertEqual(set(actual["catalog_context"]), {"zombie_abilities", "plant_abilities"})
        self.assertEqual(
            actual["plants"],
            [
                {"type_name": "sunflower", "row": 0, "col": 0, "hp": 300, "role": "resource",
                 "description_en": plant_info(1).description_en},
                {"type_name": "unknown", "row": 1, "col": 0, "hp": 300, "role": None,
                 "description_en": None},
            ],
        )


class PlantInstructionsGuidanceTests(unittest.TestCase):
    """V70/R45/R47: every plant instructions text carries anchor + experience."""

    def plant_instructions(self):
        return (
            plant_target_question({}).instructions,
            plant_lane_question({}).instructions,
            plant_lane_target_question(0, {}).instructions,
        )

    def test_all_three_anchor_direction_and_outrank_immediate_threat(self):
        for instructions in self.plant_instructions():
            self.assertIn("state.board.column_direction", instructions)
            self.assertIn("state.observed_lanes", instructions)
            self.assertIn("outranks any long-term layout preference", instructions)

    def test_all_three_include_every_bundled_experience_line(self):
        guidance = load_plant_experience()
        self.assertTrue(guidance)
        for instructions in self.plant_instructions():
            for line in guidance:
                self.assertIn(line, instructions)

    def test_editing_the_file_changes_all_three_rebuilt_questions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experience.txt"
            path.write_text(
                "Re-plant into a lane only after the first wave has been cleared.\n",
                encoding="utf-8",
            )
            with patch.object(questions, "PLANT_EXPERIENCE_PATH", path):
                self.assertEqual(
                    load_plant_experience(),
                    ("Re-plant into a lane only after the first wave has been cleared.",),
                )
                for instructions in self.plant_instructions():
                    self.assertIn(
                        "Re-plant into a lane only after the first wave has been cleared.",
                        instructions,
                    )

    def test_no_instructions_carry_a_column_rule_or_absolute_wording(self):
        for instructions in self.plant_instructions():
            for banned in ("first ", "always", "must ", "never"):
                self.assertNotIn(banned, instructions)

    def test_plant_state_fields_and_state_keys_are_unchanged(self):
        actual = build_typesafe_state(
            jev_state(cards=[plant_card(1, "sunflower", 50)], plants=[]), branch="plant"
        )
        self.assertEqual(set(actual), set(PLANT_STATE_FIELDS))

    def test_runtime_never_fails_on_over_budget_or_unknown_state_reference(self):
        over_budget = "\n".join(
            f"Guidance line {index} must not crash the plant question builder." for index in range(40)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experience.txt"
            path.write_text(f"state.whatever is not a real plant state field.\n{over_budget}\n", encoding="utf-8")
            with patch.object(questions, "PLANT_EXPERIENCE_PATH", path):
                # Over budget and referencing an unknown state field: only tests
                # guard legality, the runtime must still build questions (V72).
                question_set = build_plant_questions(
                    jev_state(cards=[plant_card(1, "sunflower", 50)], plants=[], cells=empty_cells())
                )
                self.assertTrue(question_set.questions)
