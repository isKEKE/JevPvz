"""Pre-dispatch review, fairness, and single-consumption checks for the scheduler.

Every case works on fixed State pairs, a recording Boundary stand-in, and a fake
clock: nothing here reads a game, a window, or a network. The plant and collect
targets are the ones :mod:`jev.decision` really emits, and the pairs are built by
the same :func:`state.projection.project_jev_state` the Runtime uses.
"""

from __future__ import annotations

import dataclasses
import unittest
from typing import Any, Mapping

from actions.boundary import ActionValidationError, ActionValidator
from actions.executor import ActionResult, DEFAULT_POLL_INTERVAL_MS, DEFAULT_TIMEOUT_MS
from state.projection import project_jev_state

from jev.scheduler import (
    COLLECT_CONFIRMATION_POLL_INTERVAL_MS,
    COLLECT_CONFIRMATION_TIMEOUT_MS,
    COLLECT_URGENCY,
    DISCARD_CARD_NOT_USABLE,
    DISCARD_CARD_ON_COOLDOWN,
    DISCARD_CARD_UNAVAILABLE,
    DISCARD_CELL_NOT_PLANTABLE,
    DISCARD_CELL_OCCUPIED,
    DISCARD_EPOCH_CHANGED,
    DISCARD_INSUFFICIENT_SUN,
    DISCARD_PRECONDITION_FAILED,
    DISCARD_TARGET_MISSING,
    DISCARD_TARGET_UNVERIFIABLE,
    DISCARD_TTL_EXPIRED,
    OUTCOME_DISCARDED,
    OUTCOME_EXECUTED,
    OUTCOME_REJECTED,
    PRIORITY_ORDER,
    PROPOSAL_TTL_SECONDS,
    REJECTED_VALIDATION_FAILED,
    ActionProposal,
    ActionScheduler,
    priority_rank,
    proposal_priority,
)
from jev.strategy import BRANCH_COLLECT, BRANCH_PLANT, evaluate_strategy

PEASHOOTER_CARD = {
    "slot": 0,
    "type_code": 0,
    "type_name": "peashooter",
    "cost": 100,
    "cooldown_ready": True,
    "usable": True,
}
SUNFLOWER_CARD = {
    "slot": 1,
    "type_code": 1,
    "type_name": "sunflower",
    "cost": 50,
    "cooldown_ready": True,
    "usable": True,
}
SUN_ITEM = {"type_code": 4, "type_name": "sun", "x": 100.0, "y": 200.0}
PLANT_STATUS = "2026-09-27T00:00:00.000Z"

# branch names a runtime never uses, for ordering checks over more than the two
# real branches (the queue holds one proposal per branch name).
SYNTHETIC_BRANCHES = ("b-one", "b-two", "b-three", "b-four", "b-five")


def all_state(
    sequence: int = 1,
    *,
    sun: int = 100,
    cards: list | None = None,
    occupied: tuple = (),
    plants: list | None = None,
    items: list | None = None,
    zombies: list | None = None,
    availability: Mapping[str, Any] | None = None,
    plantability: list | None = None,
) -> dict[str, Any]:
    """One All State record whose facts the real Boundary validator can prove."""
    cells = [[None] * 9 for _ in range(5)]
    for row, col, type_code, type_name in occupied:
        cells[row][col] = {"type_code": type_code, "type_name": type_name}
    return {
        "schema_version": 1,
        "sample_sequence": sequence,
        "observed_at_utc": PLANT_STATUS,
        "status": "ok",
        "valid": True,
        "decision_ready": True,
        "availability": {
            "board.occupancy": "provisional",
            "plants": "available",
            "cards": "available",
            "items": "available",
            "items.position": "available",
            **(availability or {}),
        },
        "game": {
            "phase": "playing",
            "mode": "adventure",
            "background": "day",
            "paused": False,
            "level_complete": False,
        },
        "sun_balance": sun,
        "board": {
            "rows": 5,
            "cols": 9,
            "cells": cells,
            "plantability": [[True] * 9 for _ in range(5)] if plantability is None else plantability,
        },
        "plants": list(plants or []),
        "zombies": list(zombies or []),
        "lanes": [],
        "items": list(items or []),
        "cards": list([dict(PEASHOOTER_CARD)] if cards is None else cards),
    }


def pair(sequence: int = 1, **kwargs) -> tuple[dict[str, Any], dict[str, Any]]:
    """One All State / JEV State pair, projected exactly as the Runtime does."""
    state = all_state(sequence, **kwargs)
    return state, project_jev_state(state)


def zombie(row: int, distance: int) -> dict[str, Any]:
    return {
        "type_code": 0,
        "type_name": "normal_zombie",
        "row": row,
        "hp": 270,
        "distance_to_house_cells": distance,
    }


def plant(row: int = 0, col: int = 0, *, id: int = 7, type_name: str = "peashooter") -> dict[str, Any]:
    return {"id": id, "type_code": 0, "type_name": type_name, "row": row, "col": col}


def item(id: int = 1, **kwargs) -> dict[str, Any]:
    return {"id": id, **SUN_ITEM, **kwargs}


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now


class RecordingBoundary:
    """Stand-in for :class:`actions.boundary.ActionBoundary`: same signature."""

    def __init__(self, status: str = "success", error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.requests: list[dict[str, Any]] = []
        self.states: list[tuple[Any, Any]] = []

    def dispatch(self, request: Any, *, jev_state: Mapping[str, Any], all_state: Mapping[str, Any]) -> Any:
        self.requests.append(dict(request) if isinstance(request, Mapping) else request)
        self.states.append((jev_state, all_state))
        if self.error is not None:
            raise self.error
        action = request.get("action") if isinstance(request, Mapping) else None
        return ActionResult(
            status=self.status,
            action=action,
            message="State confirmed the requested action.",
            request=dict(request),
            target={"window": "fake"},
            before_state=None,
            after_state=None,
            details={"input_clicks": []},
            started_at_utc=PLANT_STATUS,
            finished_at_utc=PLANT_STATUS,
            elapsed_ms=1,
        )


class FakeActionResult:
    """Minimal non-Boundary result object with the historical ``to_dict`` shape."""

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "status": "success", "action": None, "elapsed_ms": 0}


def plant_proposal(
    jev_state: Mapping[str, Any],
    *,
    row: int = 0,
    col: int = 0,
    created: float = 0.0,
    epoch: int = 0,
    sequence: int = 1,
    key: Any = ("plant",),
) -> ActionProposal:
    target = {"action": "place_plant", "type_name": "peashooter", "row": row, "col": col}
    urgency, premise_row = proposal_priority(BRANCH_PLANT, target, evaluate_strategy(jev_state))
    return ActionProposal(
        branch=BRANCH_PLANT,
        intent="plant",
        effective_action="plant",
        target=target,
        source_key=key,
        sample_sequence=sequence,
        epoch=epoch,
        created_monotonic=created,
        urgency=urgency,
        row=premise_row,
    )


def collect_proposal(
    *,
    type_code: int = 4,
    type_name: str = "sun",
    x: float = 100.0,
    y: float = 200.0,
    item_id: int | None = 1,
    item_index: int | None = 0,
    created: float = 0.0,
    epoch: int = 0,
    sequence: int = 1,
    key: Any = ("collect",),
) -> ActionProposal:
    """A collect proposal as the runtime builds it (OD-32: identity by item id).

    ``item_id=None`` builds the identity-less target that must never be dispatched.
    """
    target: dict[str, Any] = {
        "action": "collect_item",
        "type_code": type_code,
        "type_name": type_name,
        "x": x,
        "y": y,
    }
    if item_index is not None:
        target["item_index"] = item_index
    if item_id is not None:
        target["item_id"] = item_id
    urgency, premise_row = proposal_priority(BRANCH_COLLECT, target, None)
    return ActionProposal(
        branch=BRANCH_COLLECT,
        intent="collect",
        effective_action="collect",
        target=target,
        source_key=key,
        sample_sequence=sequence,
        epoch=epoch,
        created_monotonic=created,
        urgency=urgency,
        row=premise_row,
    )


class SchedulerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.boundary = RecordingBoundary()
        self.scheduler = ActionScheduler(self.boundary, clock=self.clock.monotonic)

    def dispatch(self, proposal: ActionProposal, latest: tuple[dict, dict], *, epoch: int = 0):
        self.scheduler.submit(proposal)
        return self.scheduler.dispatch_next(
            jev_state=latest[1], all_state=latest[0], epoch=epoch
        )

    def assertDiscarded(self, dispatch, reason: str) -> None:
        self.assertIsNotNone(dispatch)
        self.assertEqual(dispatch.outcome, OUTCOME_DISCARDED)
        self.assertEqual(dispatch.reason, reason)
        self.assertIsNone(dispatch.result)
        self.assertEqual(self.boundary.requests, [])


class PlantPreDispatchReviewTests(SchedulerCase):
    """V26: a plant target that no longer holds is discarded, never dispatched."""

    def test_discarded_when_the_sun_no_longer_covers_the_card(self):
        source, source_jev = pair(1, sun=100)
        latest = pair(2, sun=75)
        self.assertDiscarded(
            self.dispatch(plant_proposal(source_jev), latest), DISCARD_INSUFFICIENT_SUN
        )

    def test_discarded_when_the_card_is_no_longer_usable(self):
        _, source_jev = pair(1, sun=100)
        latest = pair(2, sun=100, cards=[{**PEASHOOTER_CARD, "usable": False}])
        self.assertDiscarded(
            self.dispatch(plant_proposal(source_jev), latest), DISCARD_CARD_NOT_USABLE
        )

    def test_discarded_when_the_card_is_still_cooling_down(self):
        _, source_jev = pair(1, sun=100)
        latest = pair(2, sun=100, cards=[{**PEASHOOTER_CARD, "cooldown_ready": False}])
        self.assertDiscarded(
            self.dispatch(plant_proposal(source_jev), latest), DISCARD_CARD_ON_COOLDOWN
        )

    def test_discarded_when_the_card_is_gone(self):
        _, source_jev = pair(1, sun=100)
        latest = pair(2, sun=100, cards=[SUNFLOWER_CARD])
        self.assertDiscarded(
            self.dispatch(plant_proposal(source_jev), latest), DISCARD_CARD_UNAVAILABLE
        )

    def test_discarded_when_the_target_cell_is_occupied(self):
        _, source_jev = pair(1, sun=100)
        latest = pair(2, sun=100, occupied=((0, 0, 0, "peashooter"),))
        self.assertDiscarded(
            self.dispatch(plant_proposal(source_jev), latest), DISCARD_CELL_OCCUPIED
        )

    def test_discarded_when_only_the_all_state_shows_the_cell_occupied(self):
        _, source_jev = pair(1, sun=100)
        latest_state = all_state(2, sun=100)
        latest_state["plants"] = [plant()]
        latest = (latest_state, project_jev_state(latest_state))
        self.assertDiscarded(
            self.dispatch(plant_proposal(source_jev), latest), DISCARD_CELL_OCCUPIED
        )

    def test_discarded_when_the_cell_is_no_longer_plantable(self):
        _, source_jev = pair(1, sun=100)
        grid = [[True] * 9 for _ in range(5)]
        grid[0][0] = False
        latest = pair(2, sun=100, plantability=grid)
        self.assertDiscarded(
            self.dispatch(plant_proposal(source_jev), latest), DISCARD_CELL_NOT_PLANTABLE
        )

    def test_discarded_when_the_board_facts_become_unprovable(self):
        _, source_jev = pair(1, sun=100)
        latest = pair(2, sun=100, availability={"board.occupancy": "unavailable"})
        self.assertDiscarded(
            self.dispatch(plant_proposal(source_jev), latest), DISCARD_TARGET_UNVERIFIABLE
        )

    def test_local_lane_premise_does_not_override_model_target(self):
        _, source_jev = pair(1, sun=100, zombies=[zombie(0, 2)])
        proposal = plant_proposal(source_jev)
        self.assertEqual(proposal.urgency, "high")
        latest = pair(2, sun=100)
        self.assertEqual(self.dispatch(proposal, latest).outcome, OUTCOME_EXECUTED)
        self.assertEqual(self.boundary.requests[0], proposal.target)

    def test_discarded_when_the_proposal_waited_past_its_ttl(self):
        _, source_jev = pair(1, sun=100)
        self.clock.now = PROPOSAL_TTL_SECONDS + 0.001
        latest = pair(2, sun=100)
        self.assertDiscarded(self.dispatch(plant_proposal(source_jev), latest), DISCARD_TTL_EXPIRED)

    def test_a_proposal_at_exactly_the_ttl_is_still_dispatchable(self):
        _, source_jev = pair(1, sun=100)
        self.clock.now = PROPOSAL_TTL_SECONDS
        latest = pair(2, sun=100)
        dispatch = self.dispatch(plant_proposal(source_jev), latest)
        self.assertEqual(dispatch.outcome, OUTCOME_EXECUTED)
        self.assertEqual(len(self.boundary.requests), 1)

    def test_discarded_when_the_epoch_changed(self):
        _, source_jev = pair(1, sun=100)
        latest = pair(2, sun=100)
        self.assertDiscarded(
            self.dispatch(plant_proposal(source_jev), latest, epoch=1), DISCARD_EPOCH_CHANGED
        )

    def test_an_unrelated_sample_change_never_cancels_the_proposal(self):
        _, source_jev = pair(1, sun=100, zombies=[zombie(0, 3)])
        proposal = plant_proposal(source_jev)
        latest = pair(
            2,
            sun=150,
            zombies=[zombie(0, 3), zombie(3, 1)],
            occupied=((4, 4, 0, "peashooter"),),
        )
        dispatch = self.dispatch(proposal, latest)
        self.assertEqual(dispatch.outcome, OUTCOME_EXECUTED)
        self.assertEqual(self.boundary.requests, [proposal.target])

    def test_the_model_target_is_never_replaced_or_rewritten(self):
        _, source_jev = pair(1, sun=100, occupied=((3, 8, 0, "peashooter"),))
        proposal = plant_proposal(source_jev, row=1, col=2)
        latest = pair(2, sun=150, occupied=((3, 8, 0, "peashooter"),))
        dispatch = self.dispatch(proposal, latest)
        self.assertEqual(dispatch.outcome, OUTCOME_EXECUTED)
        request = self.boundary.requests[0]
        self.assertEqual(request, {"action": "place_plant", "type_name": "peashooter", "row": 1, "col": 2})
        self.assertEqual(
            (request["type_name"], request["row"], request["col"]),
            (proposal.target["type_name"], proposal.target["row"], proposal.target["col"]),
        )
        self.assertIsNot(request, proposal.target)
        self.assertEqual(dispatch.proposal.target, proposal.target)


class CollectPreDispatchReviewTests(SchedulerCase):
    """V43 — a collect target is verified by its bound same-sample item id (OD-32).

    The identity is the item id the decision bound in its own sample, so the item may
    have moved, or the sample may hold a different number of items, and it is still
    the same target. What is never allowed is a re-bind to another item; and because
    the id is what decides, several items of one type are no longer ambiguous the way
    an exact coordinate match made them.
    """

    def test_discarded_when_the_bound_item_is_gone(self):
        proposal = collect_proposal(item_id=1)
        latest = pair(2, sun=100, items=[])
        self.assertDiscarded(self.dispatch(proposal, latest), DISCARD_TARGET_MISSING)

    def test_discarded_when_the_bound_id_is_no_longer_visible(self):
        # Other suns are visible, but they are different items: never a substitution.
        proposal = collect_proposal(item_id=1)
        latest = pair(2, sun=100, items=[item(2), item(3)])
        self.assertDiscarded(self.dispatch(proposal, latest), DISCARD_TARGET_MISSING)

    def test_several_items_of_one_type_do_not_make_the_target_ambiguous(self):
        proposal = collect_proposal(item_id=2)
        latest = pair(2, sun=100, items=[item(1), item(2), item(3)])
        dispatch = self.dispatch(proposal, latest)
        self.assertEqual(dispatch.outcome, OUTCOME_EXECUTED)
        # The Boundary is told which exact item to click through its attributes.
        self.assertEqual(self.boundary.requests[0]["item_id"], 2)
        self.assertNotIn("x", self.boundary.requests[0])
        self.assertNotIn("y", self.boundary.requests[0])

    def test_discarded_when_the_same_id_occurs_twice(self):
        proposal = collect_proposal(item_id=1)
        latest = pair(2, sun=100, items=[item(1), item(1, x=900.0)])
        self.assertDiscarded(self.dispatch(proposal, latest), DISCARD_TARGET_UNVERIFIABLE)

    def test_discarded_when_the_bound_id_now_carries_another_type(self):
        proposal = collect_proposal(item_id=1, type_code=4, type_name="sun")
        latest = pair(2, sun=100, items=[item(1, type_code=5, type_name="sun_flower")])
        self.assertDiscarded(self.dispatch(proposal, latest), DISCARD_TARGET_UNVERIFIABLE)

    def test_discarded_when_the_target_has_no_bound_identity(self):
        proposal = collect_proposal(item_id=None, item_index=None)
        latest = pair(2, sun=100, items=[item()])
        self.assertDiscarded(self.dispatch(proposal, latest), DISCARD_TARGET_MISSING)

    def test_discarded_when_the_item_position_availability_is_unproven(self):
        proposal = collect_proposal()
        latest = pair(2, sun=100, items=[item()], availability={"items.position": "unavailable"})
        self.assertDiscarded(self.dispatch(proposal, latest), DISCARD_TARGET_UNVERIFIABLE)

    def test_the_click_uses_the_current_coordinates_of_the_bound_item(self):
        # The item fell 20 px during the JEV round trip: the decision-time aim is
        # stale, and clicking it would miss. The bound id is what is verified.
        proposal = collect_proposal(item_id=1, x=100.0, y=200.0)
        latest = pair(2, sun=100, items=[item(1, x=100.0, y=220.0)])
        dispatch = self.dispatch(proposal, latest)

        self.assertEqual(dispatch.outcome, OUTCOME_EXECUTED)
        self.assertEqual(
            self.boundary.requests,
            [
                {
                    "action": "collect_item",
                    "type_code": 4,
                    "type_name": "sun",
                    "item_id": 1,
                    "timeout_ms": COLLECT_CONFIRMATION_TIMEOUT_MS,
                    "poll_interval_ms": COLLECT_CONFIRMATION_POLL_INTERVAL_MS,
                }
            ],
        )

    def test_the_bound_identity_reaches_the_boundary_without_coordinates(self):
        # The Boundary validator rejects unsupported request keys, so the bound id
        # and the option index stay on the scheduler side of the call.
        proposal = collect_proposal(item_id=7, item_index=3)
        latest = pair(2, sun=100, items=[item(7)])
        self.dispatch(proposal, latest)
        request = self.boundary.requests[0]
        self.assertEqual(set(request), {"action", "type_code", "type_name", "item_id", "timeout_ms", "poll_interval_ms"})
        self.assertEqual(dispatch_item_id(proposal), 7)

    def test_a_dropped_item_that_moved_is_still_dispatched_on_the_same_decision(self):
        # The live regression: the key no longer changes while a sun falls, so the
        # decision survives to dispatch instead of being superseded.
        proposal = collect_proposal(item_id=1, x=546.0, y=241.5695037841797)
        latest = pair(2, sun=100, items=[item(1, x=546.0, y=261.6695861816406)])
        self.assertEqual(self.dispatch(proposal, latest).outcome, OUTCOME_EXECUTED)
        self.assertEqual(self.boundary.requests[0]["item_id"], 1)
        self.assertNotIn("y", self.boundary.requests[0])


def dispatch_item_id(proposal: ActionProposal) -> Any:
    """The scheduler-side bound identity of a collect proposal."""
    return proposal.target.get("item_id")


class ShovelPreDispatchReviewTests(SchedulerCase):
    """The third existing target kind goes through the same single entry point."""

    @staticmethod
    def shovel_proposal(row: int = 0, col: int = 0) -> ActionProposal:
        return ActionProposal(
            branch=BRANCH_PLANT,
            intent="shovel",
            effective_action="shovel",
            target={"action": "shovel_cell", "row": row, "col": col},
            source_key=("shovel", row, col),
            sample_sequence=1,
            epoch=0,
            created_monotonic=0.0,
            urgency="none",
            row=None,
        )

    def test_discarded_when_the_jev_cell_has_no_plant(self):
        latest = pair(2, sun=100)
        self.assertDiscarded(
            self.dispatch(self.shovel_proposal(), latest), DISCARD_TARGET_MISSING
        )

    def test_discarded_when_only_the_jev_state_still_shows_the_plant(self):
        proposal = self.shovel_proposal()
        latest = (all_state(2, sun=100), project_jev_state(all_state(2, sun=100, occupied=((0, 0, 0, "peashooter"),))))
        self.assertDiscarded(self.dispatch(proposal, latest), DISCARD_TARGET_MISSING)

    def test_a_bound_plant_is_dispatched(self):
        latest = pair(2, sun=100, occupied=((0, 0, 0, "peashooter"),), plants=[plant()])
        dispatch = self.dispatch(self.shovel_proposal(), latest)
        self.assertEqual(dispatch.outcome, OUTCOME_EXECUTED)
        self.assertEqual(self.boundary.requests, [{"action": "shovel_cell", "row": 0, "col": 0}])


class ConsumptionTests(SchedulerCase):
    """Exactly one proposal per call, and no automatic resend of any kind."""

    def test_dispatch_next_consumes_exactly_one_proposal(self):
        _, jev_state = pair(1, sun=100, items=[item()])
        latest = pair(2, sun=100, items=[item()])
        self.scheduler.submit(plant_proposal(jev_state))
        self.scheduler.submit(collect_proposal())
        first = self.scheduler.dispatch_next(jev_state=latest[1], all_state=latest[0], epoch=0)
        self.assertIsNotNone(first)
        self.assertEqual(len(self.boundary.requests), 1)
        self.assertEqual(len(self.scheduler.pending()), 1)
        second = self.scheduler.dispatch_next(jev_state=latest[1], all_state=latest[0], epoch=0)
        self.assertIsNotNone(second)
        self.assertEqual(len(self.boundary.requests), 2)
        self.assertFalse(self.scheduler.has_pending())
        self.assertIsNone(
            self.scheduler.dispatch_next(jev_state=latest[1], all_state=latest[0], epoch=0)
        )

    def test_a_second_proposal_for_a_branch_replaces_the_pending_one(self):
        _, jev_state = pair(1, sun=100)
        first = plant_proposal(jev_state, col=0, created=0.0)
        second = plant_proposal(jev_state, col=1, created=1.0)
        self.assertIsNone(self.scheduler.submit(first))
        self.assertEqual(self.scheduler.submit(second), first)
        self.assertEqual(self.scheduler.pending("plant"), (second,))

    def test_invalidate_drops_every_pending_proposal(self):
        _, jev_state = pair(1, sun=100)
        self.scheduler.submit(plant_proposal(jev_state))
        self.scheduler.submit(collect_proposal())
        dropped = self.scheduler.invalidate("paused")
        self.assertEqual({proposal.branch for proposal in dropped}, {BRANCH_PLANT, BRANCH_COLLECT})
        self.assertFalse(self.scheduler.has_pending())

    def test_an_unverified_result_is_reported_and_never_sent_again(self):
        self.boundary.status = "unverified"
        _, jev_state = pair(1, sun=100)
        latest = pair(2, sun=100)
        dispatch = self.dispatch(plant_proposal(jev_state), latest)
        self.assertEqual(dispatch.outcome, OUTCOME_EXECUTED)
        self.assertEqual(dispatch.result.status, "unverified")
        self.assertEqual(len(self.boundary.requests), 1)
        self.assertIsNone(
            self.scheduler.dispatch_next(jev_state=latest[1], all_state=latest[0], epoch=0)
        )
        self.assertEqual(len(self.boundary.requests), 1)

    def test_a_boundary_validation_error_is_rejected_and_never_sent_again(self):
        self.boundary.error = ActionValidationError("the request is not provable")
        _, jev_state = pair(1, sun=100)
        latest = pair(2, sun=100)
        dispatch = self.dispatch(plant_proposal(jev_state), latest)
        self.assertEqual(dispatch.outcome, OUTCOME_REJECTED)
        self.assertEqual(dispatch.reason, REJECTED_VALIDATION_FAILED)
        self.assertIsNone(dispatch.result)
        self.assertEqual(len(self.boundary.requests), 1)
        self.assertIsNone(
            self.scheduler.dispatch_next(jev_state=latest[1], all_state=latest[0], epoch=0)
        )
        self.assertEqual(len(self.boundary.requests), 1)

    def test_the_dispatch_callback_fires_only_for_a_real_boundary_call(self):
        fired: list[str] = []
        scheduler = ActionScheduler(
            self.boundary, clock=self.clock.monotonic, on_dispatch=lambda _p: fired.append("x")
        )
        _, jev_state = pair(1, sun=100)
        latest = pair(2, sun=100)
        scheduler.submit(plant_proposal(jev_state))
        scheduler.dispatch_next(jev_state=latest[1], all_state=latest[0], epoch=0)
        self.assertEqual(fired, ["x"])
        scheduler.submit(plant_proposal(jev_state, epoch=9))
        scheduler.dispatch_next(jev_state=latest[1], all_state=latest[0], epoch=0)
        self.assertEqual(fired, ["x"])


class PriorityTests(unittest.TestCase):
    """V39: urgency band descending, then creation FIFO, with collect yielding."""

    def setUp(self) -> None:
        self.clock = FakeClock()
        self.boundary = RecordingBoundary()
        self.dispatched: list[str] = []
        self.scheduler = ActionScheduler(
            self.boundary,
            clock=self.clock.monotonic,
            on_dispatch=lambda proposal: self.dispatched.append(proposal.branch),
        )
        self.latest = pair(2, sun=150, items=[item()])

    def queue(self, branch: str, band: str, created: float, *, target: Mapping[str, Any] | None = None) -> ActionProposal:
        """Queue one proposal with an explicit band.

        ``row`` stays ``None``: these cases exercise the queue order and the
        collect-yield rule, not the lane premise that :func:`proposal_priority`
        derives for a real plant proposal.
        """
        proposal = ActionProposal(
            branch=branch,
            intent="plant",
            effective_action="plant",
            target=dict(target or {"action": "place_plant", "type_name": "peashooter", "row": 0, "col": 0}),
            source_key=branch,
            sample_sequence=1,
            epoch=0,
            created_monotonic=created,
            urgency=band,
            row=None,
        )
        self.scheduler.submit(proposal)
        return proposal

    def drain(self) -> list[str]:
        while self.scheduler.has_pending():
            self.scheduler.dispatch_next(
                jev_state=self.latest[1], all_state=self.latest[0], epoch=0
            )
        return list(self.dispatched)

    def test_bands_are_ordered_from_critical_down_to_none(self):
        self.assertEqual(PRIORITY_ORDER, ("none", "low", "medium", "collect", "high", "critical"))
        self.assertEqual(
            [priority_rank(band) for band in PRIORITY_ORDER], [0, 1, 2, 3, 4, 5]
        )

    def test_ready_proposals_run_by_band_then_by_creation_time(self):
        self.queue(SYNTHETIC_BRANCHES[0], "medium", 1.0)
        self.queue(SYNTHETIC_BRANCHES[1], "critical", 3.0)
        self.queue(SYNTHETIC_BRANCHES[2], "low", 0.5)
        self.queue(SYNTHETIC_BRANCHES[3], "high", 2.0)
        self.queue(SYNTHETIC_BRANCHES[4], "high", 0.1)
        self.assertEqual(
            self.drain(),
            [SYNTHETIC_BRANCHES[1], SYNTHETIC_BRANCHES[4], SYNTHETIC_BRANCHES[3],
             SYNTHETIC_BRANCHES[0], SYNTHETIC_BRANCHES[2]],
        )

    def test_same_band_is_served_first_in_first_out(self):
        self.queue(SYNTHETIC_BRANCHES[0], "high", 2.0)
        self.queue(SYNTHETIC_BRANCHES[1], "high", 1.0)
        self.assertEqual(self.drain(), [SYNTHETIC_BRANCHES[1], SYNTHETIC_BRANCHES[0]])

    def test_collect_yields_to_any_urgency_at_or_above_high(self):
        for band in ("high", "critical"):
            with self.subTest(band=band):
                self.setUp()
                collect = collect_proposal(created=0.0)
                self.scheduler.submit(collect)
                self.queue(BRANCH_PLANT, band, 5.0)
                self.assertEqual(self.drain(), [BRANCH_PLANT, BRANCH_COLLECT])

    def test_collect_outranks_low_and_medium_planting(self):
        for band in ("none", "low", "medium"):
            with self.subTest(band=band):
                self.setUp()
                self.scheduler.submit(collect_proposal(created=5.0))
                self.queue(BRANCH_PLANT, band, 0.0)
                self.assertEqual(self.drain(), [BRANCH_COLLECT, BRANCH_PLANT])

    def test_a_collect_proposal_is_dispatchable_while_a_plant_proposal_waits(self):
        # No cross-branch dependency DAG: collecting never waits for planting, and
        # an optional plant proposal that is still pending blocks nothing.
        self.scheduler.submit(collect_proposal(created=0.0))
        self.queue(BRANCH_PLANT, "low", 1.0)
        self.scheduler.dispatch_next(jev_state=self.latest[1], all_state=self.latest[0], epoch=0)
        self.assertEqual(
            [request.get("action") for request in self.boundary.requests], ["collect_item"]
        )
        self.assertEqual(len(self.scheduler.pending(BRANCH_PLANT)), 1)

    def test_a_proposal_past_its_ttl_is_discarded_and_not_replaced_automatically(self):
        self.clock.now = PROPOSAL_TTL_SECONDS + 0.5
        self.scheduler.submit(collect_proposal(created=0.0))
        dispatch = self.scheduler.dispatch_next(
            jev_state=self.latest[1], all_state=self.latest[0], epoch=0
        )
        self.assertEqual(dispatch.outcome, OUTCOME_DISCARDED)
        self.assertEqual(dispatch.reason, DISCARD_TTL_EXPIRED)
        self.assertEqual(self.boundary.requests, [])
        self.assertFalse(self.scheduler.has_pending())


class BoundaryShapeTests(SchedulerCase):
    """The Boundary contract, the result shape, and what a proposal may not carry."""

    def test_a_boundary_result_with_to_dict_is_passed_through_unchanged(self):
        result = FakeActionResult()
        self.boundary = RecordingBoundary()
        self.boundary.dispatch = lambda request, **kwargs: result  # type: ignore[assignment]
        scheduler = ActionScheduler(self.boundary, clock=self.clock.monotonic)
        self.latest = pair(2, sun=100)
        scheduler.submit(plant_proposal(pair(1, sun=100)[1]))
        dispatch = scheduler.dispatch_next(
            jev_state=self.latest[1], all_state=self.latest[0], epoch=0
        )
        self.assertIs(dispatch.result, result)
        self.assertEqual(dispatch.result.to_dict()["status"], "success")

    def test_the_boundary_receives_the_same_sample_pair_the_review_used(self):
        _, jev_state = pair(1, sun=100)
        latest = pair(2, sun=100)
        self.dispatch(plant_proposal(jev_state), latest)
        received_jev, received_all = self.boundary.states[0]
        self.assertIs(received_jev, latest[1])
        self.assertIs(received_all, latest[0])

    def test_a_proposal_carries_no_claim_reservation_funding_or_branch_dependency(self):
        fields = {field.name for field in dataclasses.fields(ActionProposal)}
        self.assertEqual(
            fields,
            {
                "branch",
                "intent",
                "effective_action",
                "target",
                "source_key",
                "source_intent",
                "source_intent_version",
                "source_cycle",
                "sample_sequence",
                "epoch",
                "created_monotonic",
                "urgency",
                "row",
            },
        )
        forbidden = ("claim", "reserve", "fund", "budget", "dependency", "dag", "await_")
        for name in dir(ActionScheduler):
            if name.startswith("_"):
                continue
            for token in forbidden:
                self.assertNotIn(token, name.lower())

    def test_a_collect_proposal_records_the_collect_band_and_no_lane_premise(self):
        proposal = collect_proposal()
        self.assertEqual(proposal.urgency, COLLECT_URGENCY)
        self.assertIsNone(proposal.row)
        self.assertLess(priority_rank(COLLECT_URGENCY), priority_rank("high"))
        self.assertGreater(priority_rank(COLLECT_URGENCY), priority_rank("medium"))

    def test_a_plant_proposal_records_the_target_lane_band(self):
        _, jev_state = pair(1, sun=100, zombies=[zombie(2, 1)])
        proposal = plant_proposal(jev_state, row=2, col=4)
        self.assertEqual(proposal.urgency, "critical")
        self.assertEqual(proposal.row, 2)
        self.assertEqual(proposal.sample_sequence, 1)
        self.assertEqual(proposal.epoch, 0)


class CollectConfirmationTimeoutTests(SchedulerCase):
    """V62/OD-47 — one collect click is confirmed on a bounded clock.

    A controlled run measured a successful collect confirmation at 1091 ms median
    and 1431 ms maximum, and one unconfirmed click blocked the only execution
    worker for 10.2 s. Only the collect request therefore carries the shorter
    budget; planting and shovelling keep the executor's 10 s default. The same
    request also carries the denser confirmation poll spacing of OD-47.
    """

    def test_every_collect_request_carries_the_bounded_confirmation_timeout(self):
        proposal = collect_proposal(item_id=1)
        latest = pair(2, sun=100, items=[item(1)])

        self.assertEqual(self.dispatch(proposal, latest).outcome, OUTCOME_EXECUTED)
        self.assertEqual(COLLECT_CONFIRMATION_TIMEOUT_MS, 2_500)
        self.assertEqual(self.boundary.requests[0]["timeout_ms"], 2_500)
        # The executor default is the plant/shovel budget and must not move.
        self.assertEqual(DEFAULT_TIMEOUT_MS, 10_000)
        self.assertLess(COLLECT_CONFIRMATION_TIMEOUT_MS, DEFAULT_TIMEOUT_MS)

    def test_the_collect_request_uses_the_denser_confirmation_poll_spacing(self):
        # The 250 ms executor default re-added a whole interval of quantization tail
        # to every collect: replaying a JEV Trace showed each success confirming
        # after 4-5 polls while one capture costs only ~53 ms. The collect request
        # therefore carries the shorter spacing, still inside the Boundary's own
        # 50 ms floor, and it stays strictly below the executor default.
        proposal = collect_proposal(item_id=1)
        latest = pair(2, sun=100, items=[item(1)])

        self.assertEqual(self.dispatch(proposal, latest).outcome, OUTCOME_EXECUTED)
        self.assertEqual(COLLECT_CONFIRMATION_POLL_INTERVAL_MS, 60)
        self.assertEqual(self.boundary.requests[0]["poll_interval_ms"], 60)
        self.assertGreaterEqual(COLLECT_CONFIRMATION_POLL_INTERVAL_MS, 50)
        self.assertLess(COLLECT_CONFIRMATION_POLL_INTERVAL_MS, DEFAULT_POLL_INTERVAL_MS)

    def test_the_denser_spacing_still_passes_the_real_boundary_validator(self):
        proposal = collect_proposal(item_id=1)
        latest = pair(2, sun=100, items=[item(1)])
        self.dispatch(proposal, latest)
        request = self.boundary.requests[0]
        jev_state, all_state_ = self.boundary.states[0]

        validated = ActionValidator().validate(
            request, jev_state=jev_state, all_state=all_state_
        )
        self.assertEqual(validated.action, "collect_item")
        self.assertEqual(
            validated.arguments["poll_interval_ms"], COLLECT_CONFIRMATION_POLL_INTERVAL_MS
        )

    def test_the_shorter_budget_still_passes_the_real_boundary_validator(self):
        proposal = collect_proposal(item_id=1)
        latest = pair(2, sun=100, items=[item(1)])
        self.dispatch(proposal, latest)
        request = self.boundary.requests[0]
        jev_state, all_state_ = self.boundary.states[0]

        validated = ActionValidator().validate(
            request, jev_state=jev_state, all_state=all_state_
        )
        self.assertEqual(validated.action, "collect_item")
        self.assertEqual(validated.arguments["timeout_ms"], COLLECT_CONFIRMATION_TIMEOUT_MS)

    def test_plant_and_shovel_requests_keep_the_executor_default(self):
        # Neither request is rewritten: with no timeout of its own, the executor's
        # 10 s default applies exactly as before (OD-47).
        _, jev_state = pair(1, sun=100)
        plant_latest = pair(2, sun=100)
        self.scheduler.submit(plant_proposal(jev_state))
        self.scheduler.dispatch_next(jev_state=plant_latest[1], all_state=plant_latest[0], epoch=0)
        self.assertNotIn("timeout_ms", self.boundary.requests[0])

        shovel_latest = pair(3, sun=100, occupied=((0, 0, 0, "peashooter"),), plants=[plant()])
        self.scheduler.submit(ShovelPreDispatchReviewTests.shovel_proposal())
        self.scheduler.dispatch_next(jev_state=shovel_latest[1], all_state=shovel_latest[0], epoch=0)
        self.assertEqual(len(self.boundary.requests), 2)
        self.assertNotIn("timeout_ms", self.boundary.requests[1])


if __name__ == "__main__":
    unittest.main()
