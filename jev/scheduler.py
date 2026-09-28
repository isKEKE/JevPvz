"""Unified action dispatch: one execution worker, pre-dispatch review, fairness.

Authorities: OD-22 (proposal TTL 5 s, the invalidation order epoch -> branch key
-> pre-dispatch review -> TTL, and fairness: a single non-preemptible execution
worker, ready proposals ordered by urgency band descending then creation FIFO,
``collect`` yielding to any urgency >= ``high``, and a proposal past its TTL
discarded and handed back to its branch), OD-24 (a complete action -- select,
click, confirm -- is never interleaved with another), OD-27 (no collect -> plant
dependency DAG, no funding task, no resource reservation), OD-32 (a collect target
binds the same sample's item id and is re-verified by that id at dispatch; the click
uses the item's current coordinates, while the bound id may never be replaced by
another item), OD-47 (a collect request carries its own bounded confirmation
timeout, so an unconfirmed click cannot hold the only execution worker for the
executor's 10 s default) and the T6/T8 task rows of P03.

:class:`ActionScheduler` keeps at most one pending :class:`ActionProposal` per
branch and consumes exactly one proposal per :meth:`ActionScheduler.dispatch_next`
call. The proposal is reviewed against the newest reliable State pair with the
same fail-closed sample semantics the :class:`actions.boundary.ActionBoundary`
validator applies -- plus the resource facts the validator does not check -- and
the reviewed target is then dispatched through the unchanged
``ActionBoundary.dispatch(request, jev_state=..., all_state=...)`` entry point, so
the returned :class:`actions.executor.ActionResult` keeps the shape
``jev/trace.py`` and ``main.py`` already read.

Nothing is reserved, funded, or predicted: only the current ``sun``, the current
cards, and the current board decide whether a proposal is still executable.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Hashable, Mapping

from actions.boundary import ActionValidationError

from .strategy import BRANCH_COLLECT, BRANCH_PLANT, evaluate_strategy

PROPOSAL_TTL_SECONDS = 5.0
"""A proposal that waited this long is discarded and handed back (OD-22)."""

COLLECT_CONFIRMATION_TIMEOUT_MS = 2_500
"""Confirmation budget of one collect request (OD-47, R36).

The executor's ``DEFAULT_TIMEOUT_MS`` stays 10 s because planting and shovelling
need the longer budget; a controlled run measured a successful collect
confirmation at 1091 ms median and 1431 ms maximum, while a single unconfirmed
collect click blocked the only execution worker for 10.2 s and dropped a visible
sun. Only the collect request therefore carries this bounded budget.
"""

COLLECT_CONFIRMATION_POLL_INTERVAL_MS = 60
"""Poll spacing of one collect confirmation (OD-47, R36).

A JEV Trace replay measured every successful collect confirming after 4-5 polls
at the executor's 250 ms default: the game clears the item from its item list
only ~550-800 ms after the click, while one All State capture costs only ~53 ms.
The 250 ms spacing therefore added up to a whole interval of pure quantization
tail to every collect (measured boundary elapsed 1014-1391 ms against 796-1093 ms
of actual waiting). Asking every 60 ms keeps every poll cheap, cuts that tail to
at most 60 ms, and does not weaken the bounded budget: the request still stops at
``COLLECT_CONFIRMATION_TIMEOUT_MS``. The value sits at the Boundary's own 50 ms
floor with one interval of headroom.
"""

URGENCY_BANDS = ("none", "low", "medium", "high", "critical")
"""The OD-30 ordered lane bands, lowest first."""

COLLECT_URGENCY = "collect"
"""Scheduling band of a collect proposal, which has no lane premise.

It ranks between ``medium`` and ``high``: a collect proposal always yields to a
defense-grade proposal (OD-22: any urgency >= ``high``) while it still outranks
optional ``low``/``medium`` planting.
"""

PRIORITY_ORDER = ("none", "low", "medium", COLLECT_URGENCY, "high", "critical")
"""Scheduling order, lowest first; ranking is by band, never by branch name."""

OUTCOME_EXECUTED = "executed"
OUTCOME_DISCARDED = "discarded"
OUTCOME_REJECTED = "action_rejected"

DISCARD_EPOCH_CHANGED = "epoch_changed"
DISCARD_PROPOSAL_REPLACED = "proposal_replaced"
DISCARD_TARGET_MISSING = "target_missing"
DISCARD_TARGET_UNVERIFIABLE = "target_unverifiable"
DISCARD_CARD_UNAVAILABLE = "card_unavailable"
DISCARD_CARD_NOT_USABLE = "card_not_usable"
DISCARD_CARD_ON_COOLDOWN = "card_on_cooldown"
DISCARD_INSUFFICIENT_SUN = "insufficient_sun"
DISCARD_CELL_OCCUPIED = "cell_occupied"
DISCARD_CELL_NOT_PLANTABLE = "cell_not_plantable"
DISCARD_PRECONDITION_FAILED = "precondition_no_longer_holds"
DISCARD_TTL_EXPIRED = "proposal_expired"
REJECTED_VALIDATION_FAILED = "action_validation_failed"

_PLANT_ACTION = "place_plant"
_COLLECT_ACTION = "collect_item"
_SHOVEL_ACTION = "shovel_cell"
_AVAILABILITY = frozenset({"available", "provisional"})
_PRIORITY_RANK = {band: rank for rank, band in enumerate(PRIORITY_ORDER)}


def priority_rank(band: str) -> int:
    """Return the scheduling rank of one band; an unknown band ranks lowest."""
    return _PRIORITY_RANK.get(band, -1)


@dataclass(frozen=True)
class ActionProposal:
    """One branch's ready target, bound to the pair, key and premise it came from.

    ``target`` is the model's own target, stored verbatim: dispatch copies it into
    the Boundary request and never rewrites ``type_name``/``row``/``col`` and
    never swaps in another entity. ``urgency``/``row`` are the recorded premise --
    the ordered band of the lane the target plants into -- which the pre-dispatch
    review re-derives from the newest State. ``source_key`` is the branch's
    semantic key at submit time, so a discard can hand the branch back only when
    it has not already decided something newer.
    """

    branch: str
    intent: str
    effective_action: str
    target: dict[str, Any]
    source_key: Hashable
    sample_sequence: int | None
    epoch: int
    created_monotonic: float
    urgency: str
    row: int | None = None
    source_intent_version: int | None = None
    source_intent: dict[str, Any] | None = None
    source_cycle: int | None = None

    def age_seconds(self, now: float) -> float:
        """How long this proposal has been waiting, in seconds."""
        return now - self.created_monotonic


@dataclass(frozen=True)
class ActionDispatch:
    """The result of consuming exactly one proposal."""

    proposal: ActionProposal
    outcome: str
    reason: str | None
    result: Any | None


def proposal_priority(
    branch: str,
    target: Mapping[str, Any],
    signals: Any | None,
) -> tuple[str, int | None]:
    """Return the scheduling band and the lane premise of one branch's target.

    A plant target carries the ordered urgency band of the lane it plants into, so
    the review can re-derive that band from the newest State; a collect proposal
    has no lane premise and carries :data:`COLLECT_URGENCY`.
    """
    if branch == BRANCH_COLLECT:
        return COLLECT_URGENCY, None
    if branch == BRANCH_PLANT:
        row = target.get("row")
        rows = () if signals is None else signals.rows
        if _is_int(row) and 0 <= row < len(rows):
            return rows[row].urgency, row
        return URGENCY_BANDS[0], None
    raise ValueError(f"unsupported proposal branch: {branch!r}")


class ActionScheduler:
    """One pending proposal per branch, one non-preemptible execution worker.

    ``submit`` and :meth:`invalidate` are called from the Runtime's event-loop
    thread while :meth:`dispatch_next` may run in a worker thread, so the queue
    itself is lock-guarded. The blocking Boundary call happens outside the lock:
    an action that is already in flight is neither cancelled nor rewritten, and
    no second action can start while it runs.
    """

    def __init__(
        self,
        boundary: Any,
        *,
        clock: Callable[[], float] = time.monotonic,
        proposal_ttl_seconds: float = PROPOSAL_TTL_SECONDS,
        on_dispatch: Callable[[ActionProposal], None] | None = None,
        source_guard: Callable[[ActionProposal], str | None] | None = None,
    ):
        self._boundary = boundary
        self._clock = clock
        self._proposal_ttl = proposal_ttl_seconds
        self._on_dispatch = on_dispatch
        self._source_guard = source_guard
        self._pending: dict[str, ActionProposal] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ queue front

    def submit(self, proposal: ActionProposal) -> ActionProposal | None:
        """Adopt ``proposal`` as its branch's only pending proposal.

        Latest-only (OD-26): a second proposal for the same branch replaces the
        pending one, which is returned so the caller can record the replacement.
        The newest decision always wins because it is bound to the newest pair.
        """
        with self._lock:
            replaced = self._pending.get(proposal.branch)
            self._pending[proposal.branch] = proposal
        return replaced

    def pending(self, branch: str | None = None) -> tuple[ActionProposal, ...]:
        """The pending proposal(s); a whole-queue read is in insertion order."""
        with self._lock:
            if branch is None:
                return tuple(self._pending.values())
            proposal = self._pending.get(branch)
        return () if proposal is None else (proposal,)

    def has_pending(self) -> bool:
        with self._lock:
            return bool(self._pending)

    def invalidate(self, reason: str) -> tuple[ActionProposal, ...]:
        """Drop every pending proposal; the reason is the caller's to record."""
        with self._lock:
            dropped = tuple(self._pending.values())
            self._pending.clear()
        return dropped

    def next_proposal(self) -> ActionProposal | None:
        """The readiest pending proposal: urgency band descending, then FIFO."""
        with self._lock:
            pending = tuple(self._pending.values())
        if not pending:
            return None
        return min(pending, key=_order_key)

    # ------------------------------------------------------------- dispatch

    def review(
        self,
        proposal: ActionProposal,
        *,
        jev_state: Mapping[str, Any],
        all_state: Mapping[str, Any],
        epoch: int,
    ) -> str | None:
        """Return the discard reason for ``proposal``, or ``None`` when dispatchable.

        The checks follow the OD-22 order: the epoch first, then the target's
        identity and resources in the newest pair, then the recorded premise, and
        only last the proposal TTL. Nothing here can replace the model's target;
        every failure throws the proposal away, and the branch decides again --
        right after a TTL discard, otherwise as soon as the State fact that voided
        the target changes its ``build_branch_state_key``.
        """
        return self._resolve(
            proposal, jev_state=jev_state, all_state=all_state, epoch=epoch
        )[0]

    def _resolve(
        self,
        proposal: ActionProposal,
        *,
        jev_state: Mapping[str, Any],
        all_state: Mapping[str, Any],
        epoch: int,
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Return ``(discard_reason, boundary_request)`` for one proposal.

        The verdict and the request come out of one pass over the newest pair, so
        the target that was verified is exactly the target that is sent. A collect
        request additionally carries the click coordinates of the current sample
        instead of the ones the model answered about (OD-32): the bound item id is
        what was verified, and the click goes wherever that same item is *now*. A
        rejected proposal returns its reason together with ``None``.
        """
        if proposal.epoch != epoch:
            return DISCARD_EPOCH_CHANGED, None
        if self._source_guard is not None:
            source_reason = self._source_guard(proposal)
            if source_reason is not None: return source_reason, None
        target = proposal.target
        action = target.get("action")
        if action == _PLANT_ACTION:
            reason = _review_plant(proposal, target, jev_state, all_state)
        elif action == _COLLECT_ACTION:
            reason = _review_collect(target, all_state)
        elif action == _SHOVEL_ACTION:
            reason = _review_shovel(target, jev_state, all_state)
        else:
            reason = DISCARD_TARGET_MISSING
        if reason is not None:
            return reason, None
        if proposal.age_seconds(self._clock()) > self._proposal_ttl:
            return DISCARD_TTL_EXPIRED, None
        return None, _dispatch_request(target, all_state)

    def dispatch_next(
        self,
        *,
        jev_state: Mapping[str, Any],
        all_state: Mapping[str, Any],
        epoch: int,
    ) -> ActionDispatch | None:
        """Consume exactly one ready proposal: review it, then dispatch or discard.

        The proposal leaves the queue either way, so one call never dispatches a
        second action, never retries an ``unverified`` result, and never re-sends
        a target the Boundary rejected. ``on_dispatch`` fires at the moment the
        Boundary call is entered, so a dispatch the stop gate cancels mid-flight is
        still counted as a real dispatch.
        """
        proposal = self._take_next()
        if proposal is None:
            return None
        reason, request = self._resolve(
            proposal, jev_state=jev_state, all_state=all_state, epoch=epoch
        )
        if reason is not None:
            return ActionDispatch(
                proposal=proposal, outcome=OUTCOME_DISCARDED, reason=reason, result=None
            )
        if self._on_dispatch is not None:
            self._on_dispatch(proposal)
        try:
            result = self._boundary.dispatch(request, jev_state=jev_state, all_state=all_state)
        except ActionValidationError:
            return ActionDispatch(
                proposal=proposal,
                outcome=OUTCOME_REJECTED,
                reason=REJECTED_VALIDATION_FAILED,
                result=None,
            )
        return ActionDispatch(
            proposal=proposal, outcome=OUTCOME_EXECUTED, reason=None, result=result
        )

    def _take_next(self) -> ActionProposal | None:
        with self._lock:
            if not self._pending:
                return None
            proposal = min(self._pending.values(), key=_order_key)
            del self._pending[proposal.branch]
            return proposal


def _order_key(proposal: ActionProposal) -> tuple[int, float]:
    return (-priority_rank(proposal.urgency), proposal.created_monotonic)


def _review_plant(
    proposal: ActionProposal,
    target: Mapping[str, Any],
    jev_state: Mapping[str, Any],
    all_state: Mapping[str, Any],
) -> str | None:
    row, col = target.get("row"), target.get("col")
    type_name = target.get("type_name")
    if not _is_int(row) or not _is_int(col) or not isinstance(type_name, str) or not type_name:
        return DISCARD_TARGET_MISSING
    card = _unique_card(jev_state, type_name)
    if card is None:
        return DISCARD_CARD_UNAVAILABLE
    if card.get("usable") is not True:
        return DISCARD_CARD_NOT_USABLE
    if card.get("cooldown_ready") is not True:
        return DISCARD_CARD_ON_COOLDOWN
    cost, sun = card.get("cost"), _sun_balance(jev_state)
    if not _is_int(cost) or sun is None or sun < cost:
        return DISCARD_INSUFFICIENT_SUN
    occupancy = _cell_occupancy(jev_state, all_state, row, col)
    if occupancy == "occupied":
        return DISCARD_CELL_OCCUPIED
    if occupancy == "not_plantable":
        return DISCARD_CELL_NOT_PLANTABLE
    if occupancy == "unverifiable":
        return DISCARD_TARGET_UNVERIFIABLE
    return None


def _review_collect(
    target: Mapping[str, Any],
    all_state: Mapping[str, Any],
) -> str | None:
    """Verify the target's bound item id against the newest All State (OD-32).

    The identity is the item ``id`` the decision bound in its own sample, so the
    item may have moved in the meantime -- or the sample may hold a different number
    of items -- and it is still the same target. What may never happen is a
    re-bind: an id that is gone, or that now carries another ``type_code`` or
    ``type_name``, is a discard and never a substitution. Because a collectable
    item's id is unique per sample, several items of one type can no longer make a
    target ambiguous the way an exact coordinate match did; that is also why the
    coordinates themselves are no longer compared here.
    """
    item_id = target.get("item_id")
    type_code = target.get("type_code")
    type_name = target.get("type_name")
    if (
        not _is_int(item_id)
        or item_id <= 0
        or not _is_int(type_code)
        or type_code < 0
        or not isinstance(type_name, str)
        or not type_name
    ):
        # Without the same-sample identity of OD-32 nothing could be verified.
        return DISCARD_TARGET_MISSING
    availability = all_state.get("availability")
    if (
        not isinstance(availability, Mapping)
        or availability.get("items") not in _AVAILABILITY
        or availability.get("items.position") not in _AVAILABILITY
        or not isinstance(all_state.get("items"), list)
    ):
        return DISCARD_TARGET_UNVERIFIABLE
    matches = _item_matches(all_state, item_id)
    if not matches:
        return DISCARD_TARGET_MISSING
    if len(matches) != 1:
        return DISCARD_TARGET_UNVERIFIABLE
    record = matches[0]
    if record.get("type_code") != type_code or record.get("type_name") != type_name:
        return DISCARD_TARGET_UNVERIFIABLE
    if not _is_number(record.get("x")) or not _is_number(record.get("y")):
        return DISCARD_TARGET_UNVERIFIABLE
    return None


def _dispatch_request(
    target: Mapping[str, Any],
    all_state: Mapping[str, Any],
) -> dict[str, Any]:
    """The Boundary request for a target that has already passed review.

    Only a collect request is rewritten, and only its aim: the coordinates come from
    the item the review just verified in the current sample, so an item that fell
    during the JEV round trip is clicked where it is now. ``_review_collect`` has
    already proved that the id is present and agrees with the bound identity, so the
    recorded coordinates are left untouched only if that record cannot be resolved,
    which would mean the freshly reviewed sample was replaced in between; aim is
    never taken from a different item.

    ``item_index`` and the decision-time ``x``/``y`` are scheduler-side leftovers and
    are removed here: the collect target is bound by ``item_id`` (OD-34/T11), which is
    the identity the Boundary validates, and the Executor resolves the click point
    from that id against the live sample.

    A collect request also carries the bounded confirmation timeout and poll
    spacing of OD-47: a click State never confirms must come back quickly, because
    it holds the only execution worker for as long as it waits. Plant and shovel
    requests are left exactly as the proposal's target was, so the executor's own
    defaults apply.
    """
    request = dict(target)
    if request.get("action") == _COLLECT_ACTION:
        request.pop("item_index", None)
        request.pop("x", None)
        request.pop("y", None)
        request["timeout_ms"] = COLLECT_CONFIRMATION_TIMEOUT_MS
        request["poll_interval_ms"] = COLLECT_CONFIRMATION_POLL_INTERVAL_MS
    return request


def _review_shovel(
    target: Mapping[str, Any],
    jev_state: Mapping[str, Any],
    all_state: Mapping[str, Any],
) -> str | None:
    row, col = target.get("row"), target.get("col")
    cells = _board_cells(jev_state)
    if not _is_int(row) or not _is_int(col) or cells is None:
        return DISCARD_TARGET_MISSING
    if not (0 <= row < len(cells) and 0 <= col < len(cells[row])):
        return DISCARD_TARGET_MISSING
    cell = cells[row][col]
    if not (isinstance(cell, str) and cell.startswith("plant:")):
        return DISCARD_TARGET_MISSING
    plants = all_state.get("plants")
    availability = all_state.get("availability")
    if (
        not isinstance(availability, Mapping)
        or availability.get("plants") not in _AVAILABILITY
        or not isinstance(plants, list)
    ):
        return DISCARD_TARGET_UNVERIFIABLE
    type_name = cell[len("plant:"):]
    if not any(
        isinstance(plant, Mapping)
        and plant.get("row") == row
        and plant.get("col") == col
        and plant.get("type_name") == type_name
        for plant in plants
    ):
        return DISCARD_TARGET_MISSING
    return None


def _lane_still_needs_response(proposal: ActionProposal, jev_state: Mapping[str, Any]) -> bool:
    """Does the recorded lane premise still hold in the newest State?

    The recorded premise is the lane's ordered urgency band; the lane still needs
    its response while the newest band is at least that urgent. A lane whose facts
    became unreadable falls to ``none`` and therefore fails closed.
    """
    signals = evaluate_strategy(jev_state)
    row = proposal.row
    if row is None or not 0 <= row < len(signals.rows):
        return False
    return priority_rank(signals.rows[row].urgency) >= priority_rank(proposal.urgency)


def _cell_occupancy(
    jev_state: Mapping[str, Any],
    all_state: Mapping[str, Any],
    row: int,
    col: int,
) -> str:
    """``empty``, ``occupied``, ``not_plantable``, or ``unverifiable``."""
    cells = _board_cells(jev_state)
    if cells is None or not (0 <= row < len(cells) and 0 <= col < len(cells[row])):
        return "unverifiable"
    cell = cells[row][col]
    if isinstance(cell, str) and cell.startswith("plant:"):
        return "occupied"
    if cell is False:
        return "not_plantable"
    if cell is not None:
        return "unverifiable"
    plants = all_state.get("plants")
    availability = all_state.get("availability")
    if (
        not isinstance(availability, Mapping)
        or availability.get("plants") not in _AVAILABILITY
        or not isinstance(plants, list)
    ):
        return "unverifiable"
    if any(
        isinstance(plant, Mapping) and plant.get("row") == row and plant.get("col") == col
        for plant in plants
    ):
        return "occupied"
    return "empty"


def _unique_card(jev_state: Mapping[str, Any], type_name: str) -> Mapping[str, Any] | None:
    cards = jev_state.get("cards")
    if not isinstance(cards, list):
        return None
    matches = [
        card for card in cards
        if isinstance(card, Mapping) and card.get("type_name") == type_name
    ]
    return matches[0] if len(matches) == 1 else None


def _board_cells(jev_state: Mapping[str, Any]) -> list[Any] | None:
    board = jev_state.get("board")
    cells = board.get("cells") if isinstance(board, Mapping) else None
    if (
        not isinstance(cells, list)
        or not cells
        or any(not isinstance(row, list) for row in cells)
    ):
        return None
    return cells


def _sun_balance(jev_state: Mapping[str, Any]) -> int | None:
    value = jev_state.get("sun_balance")
    return value if _is_int(value) and value >= 0 else None


def _item_matches(all_state: Mapping[str, Any], item_id: Any) -> list[Mapping[str, Any]]:
    """Every All State item record carrying ``item_id``.

    A collectable item's id is unique per sample, so anything but exactly one match
    is a failed verification rather than a reason to pick one of them.
    """
    if not isinstance(all_state, Mapping) or not _is_int(item_id):
        return []
    items = all_state.get("items")
    if not isinstance(items, list):
        return []
    return [
        item for item in items
        if isinstance(item, Mapping) and item.get("id") == item_id
    ]


def _item_record(all_state: Mapping[str, Any], item_id: Any) -> Mapping[str, Any] | None:
    """The unique All State item record carrying ``item_id``, else ``None``."""
    matches = _item_matches(all_state, item_id)
    return matches[0] if len(matches) == 1 else None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


__all__ = [
    "ActionDispatch",
    "ActionProposal",
    "ActionScheduler",
    "COLLECT_CONFIRMATION_POLL_INTERVAL_MS",
    "COLLECT_CONFIRMATION_TIMEOUT_MS",
    "COLLECT_URGENCY",
    "DISCARD_CARD_NOT_USABLE",
    "DISCARD_CARD_ON_COOLDOWN",
    "DISCARD_CARD_UNAVAILABLE",
    "DISCARD_CELL_NOT_PLANTABLE",
    "DISCARD_CELL_OCCUPIED",
    "DISCARD_EPOCH_CHANGED",
    "DISCARD_INSUFFICIENT_SUN",
    "DISCARD_PRECONDITION_FAILED",
    "DISCARD_PROPOSAL_REPLACED",
    "DISCARD_TARGET_MISSING",
    "DISCARD_TARGET_UNVERIFIABLE",
    "DISCARD_TTL_EXPIRED",
    "OUTCOME_DISCARDED",
    "OUTCOME_EXECUTED",
    "OUTCOME_REJECTED",
    "PRIORITY_ORDER",
    "PROPOSAL_TTL_SECONDS",
    "REJECTED_VALIDATION_FAILED",
    "URGENCY_BANDS",
    "priority_rank",
    "proposal_priority",
]
