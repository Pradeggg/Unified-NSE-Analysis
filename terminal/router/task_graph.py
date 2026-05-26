"""AA-CC-4: Task dependency graph for router tool plans.

Inspired by Claude Code's task graph (``addBlocks`` / ``addBlockedBy``).
Lets a provider declare *which* tool calls block *which* — instead of
encoding execution order purely by tuple position. Independent calls
become discoverable as parallel layers, and cycles become detectable.

Design
------
:class:`terminal.router.schema.ToolCallSpec` was extended (additively)
with two optional fields:

* ``task_id`` — a short stable identifier for the node, e.g.
  ``"resolve"`` or ``"intraday_setup"``. Empty string means "no
  explicit id" and the helpers will mint one from the index.
* ``blocked_by`` — a tuple of ``task_id`` strings that must complete
  before this call may run.

Existing call sites that ignore these fields keep working unchanged;
sequential tuple order is the natural default.

API
---
* :func:`add_blocks(specs, blocker_id, *blocked_ids)` — annotate
  ``blocked_ids`` so each is ``blocked_by`` the ``blocker_id``.
* :func:`add_blocked_by(specs, blocked_id, *blocker_ids)` — annotate
  ``blocked_id`` with the ``blocker_ids`` as dependencies.
* :func:`topological_order(specs)` — return specs in a valid
  execution order; raises ``ValueError`` on cycles or missing IDs.
* :func:`dependency_layers(specs)` — return ``list[tuple[ToolCallSpec, ...]]``
  where each inner tuple is a layer of mutually-independent calls
  that *could* run in parallel.
* :func:`validate(specs)` — raise ``ValueError`` on cycles or
  references to unknown task IDs.

Camel-case aliases ``addBlocks`` / ``addBlockedBy`` are exported for
symmetry with the Claude Code surface.
"""
from __future__ import annotations

from typing import Iterable

from .schema import ToolCallSpec


def _ensure_ids(specs: Iterable[ToolCallSpec]) -> tuple[ToolCallSpec, ...]:
    """Mint synthetic IDs (``t0``, ``t1``, …) for any spec without one.

    Returns a new tuple; the input is not mutated. Synthetic IDs are
    only minted when needed — already-id'd specs are untouched.
    """
    out: list[ToolCallSpec] = []
    used: set[str] = {s.task_id for s in specs if s.task_id}
    for idx, spec in enumerate(specs):
        if spec.task_id:
            out.append(spec)
            continue
        candidate = f"t{idx}"
        while candidate in used:
            candidate += "_"
        used.add(candidate)
        out.append(spec.with_deps(task_id=candidate))
    return tuple(out)


def _index_by_id(specs: Iterable[ToolCallSpec]) -> dict[str, int]:
    out: dict[str, int] = {}
    for idx, spec in enumerate(specs):
        if not spec.task_id:
            raise ValueError(
                f"ToolCallSpec at index {idx} has no task_id; call _ensure_ids first."
            )
        if spec.task_id in out:
            raise ValueError(f"Duplicate task_id {spec.task_id!r} in plan.")
        out[spec.task_id] = idx
    return out


def add_blocks(
    specs: Iterable[ToolCallSpec],
    blocker_id: str,
    *blocked_ids: str,
) -> tuple[ToolCallSpec, ...]:
    """Annotate ``blocked_ids`` with a dependency on ``blocker_id``.

    Semantically: ``blocker_id`` *blocks* ``blocked_ids`` — i.e. the
    blocker must finish before any of the blocked tasks may run.
    """
    if not blocker_id:
        raise ValueError("blocker_id must be non-empty.")
    if not blocked_ids:
        return tuple(specs)
    specs_t = _ensure_ids(specs)
    idx = _index_by_id(specs_t)
    if blocker_id not in idx:
        raise ValueError(f"Unknown blocker task_id {blocker_id!r}.")
    blocked_set = set(blocked_ids)
    unknown = blocked_set - idx.keys()
    if unknown:
        raise ValueError(f"Unknown blocked task_ids: {sorted(unknown)}.")
    if blocker_id in blocked_set:
        raise ValueError(f"Task {blocker_id!r} cannot block itself.")
    out = list(specs_t)
    for bid in blocked_ids:
        node = out[idx[bid]]
        if blocker_id in node.blocked_by:
            continue
        out[idx[bid]] = node.with_deps(
            blocked_by=tuple(node.blocked_by) + (blocker_id,)
        )
    return tuple(out)


def add_blocked_by(
    specs: Iterable[ToolCallSpec],
    blocked_id: str,
    *blocker_ids: str,
) -> tuple[ToolCallSpec, ...]:
    """Annotate ``blocked_id`` so it is blocked by each of ``blocker_ids``.

    The inverse of :func:`add_blocks` — same graph, different
    builder direction. Useful when the *dependent* task is the one
    you have in hand.
    """
    if not blocked_id:
        raise ValueError("blocked_id must be non-empty.")
    if not blocker_ids:
        return tuple(specs)
    specs_t = _ensure_ids(specs)
    idx = _index_by_id(specs_t)
    if blocked_id not in idx:
        raise ValueError(f"Unknown blocked task_id {blocked_id!r}.")
    unknown = set(blocker_ids) - idx.keys()
    if unknown:
        raise ValueError(f"Unknown blocker task_ids: {sorted(unknown)}.")
    if blocked_id in blocker_ids:
        raise ValueError(f"Task {blocked_id!r} cannot block itself.")
    out = list(specs_t)
    node = out[idx[blocked_id]]
    new_deps = list(node.blocked_by)
    for bid in blocker_ids:
        if bid not in new_deps:
            new_deps.append(bid)
    out[idx[blocked_id]] = node.with_deps(blocked_by=tuple(new_deps))
    return tuple(out)


def validate(specs: Iterable[ToolCallSpec]) -> None:
    """Raise ``ValueError`` on cycles, unknown IDs, or duplicate IDs."""
    specs_t = tuple(specs)
    if not specs_t:
        return
    idx = _index_by_id(specs_t)
    for spec in specs_t:
        unknown = set(spec.blocked_by) - idx.keys()
        if unknown:
            raise ValueError(
                f"Task {spec.task_id!r} blocked_by unknown ids: {sorted(unknown)}."
            )
        if spec.task_id in spec.blocked_by:
            raise ValueError(f"Task {spec.task_id!r} is blocked by itself.")
    # Cycle detection via DFS with WHITE/GRAY/BLACK colouring.
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {s.task_id: WHITE for s in specs_t}
    by_id = {s.task_id: s for s in specs_t}

    def dfs(node_id: str, stack: list[str]) -> None:
        color[node_id] = GRAY
        for dep in by_id[node_id].blocked_by:
            if color[dep] == GRAY:
                cycle = stack[stack.index(dep):] + [dep]
                raise ValueError(f"Cycle in task graph: {' -> '.join(cycle)}.")
            if color[dep] == WHITE:
                dfs(dep, stack + [dep])
        color[node_id] = BLACK

    for spec in specs_t:
        if color[spec.task_id] == WHITE:
            dfs(spec.task_id, [spec.task_id])


def topological_order(specs: Iterable[ToolCallSpec]) -> tuple[ToolCallSpec, ...]:
    """Return ``specs`` in a valid execution order.

    Stable: within a layer, original input order is preserved.
    """
    specs_t = _ensure_ids(specs)
    validate(specs_t)
    out: list[ToolCallSpec] = []
    for layer in dependency_layers(specs_t):
        out.extend(layer)
    return tuple(out)


def dependency_layers(
    specs: Iterable[ToolCallSpec],
) -> list[tuple[ToolCallSpec, ...]]:
    """Group ``specs`` into layers of mutually-independent calls.

    Layer ``k`` contains every spec whose every dependency is in
    layer ``< k``. Within a layer, original input order is preserved
    so the output is deterministic. Each layer can in principle be
    dispatched in parallel.
    """
    specs_t = _ensure_ids(specs)
    validate(specs_t)
    remaining = list(specs_t)
    placed: set[str] = set()
    layers: list[tuple[ToolCallSpec, ...]] = []
    while remaining:
        layer: list[ToolCallSpec] = []
        next_remaining: list[ToolCallSpec] = []
        for spec in remaining:
            if all(dep in placed for dep in spec.blocked_by):
                layer.append(spec)
            else:
                next_remaining.append(spec)
        if not layer:
            raise ValueError(
                "dependency_layers stuck — unsatisfied deps among "
                f"{[s.task_id for s in remaining]}."
            )
        for spec in layer:
            placed.add(spec.task_id)
        layers.append(tuple(layer))
        remaining = next_remaining
    return layers


# Camel-case aliases (Claude Code surface compatibility).
addBlocks = add_blocks
addBlockedBy = add_blocked_by


__all__ = [
    "add_blocks",
    "add_blocked_by",
    "addBlocks",
    "addBlockedBy",
    "validate",
    "topological_order",
    "dependency_layers",
]
