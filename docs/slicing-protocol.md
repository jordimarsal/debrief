# Slicing protocol

> Installed by the `vertical-slices` module. Read this before cutting a
> user-facing feature into increments.
> One goal: every increment is demoable value, not a half-layer.

## When to slice

Use slices when the feature is **user-facing and spans UI/API/persistence** —
anything a human could watch working end-to-end. Do not slice infrastructure
or library work (a migration, a parser, a client SDK): no user-visible
increment exists, and forced slices become horizontal layers in disguise.
Those features keep the classic single-spec flow.

## The slice map

1. The leader drafts an ordered map of slices — one line each:
   `S<n> | name | user outcome | acceptance subset`.
2. The map goes into a `## Slice Map` section in the **parent** feature's
   `design.md`, together with the cross-slice architectural decisions (ADRs).
3. The parent's Spec Gate approves the map. Slicing decisions are design
   decisions — they are reviewed there, not in a new gate.

S1 is the **walking skeleton**: the thinnest path through the real
architecture (UI → API → persistence), real stack, no mocks. It proves the
shape, not the breadth. Later slices add one behavior each, ordered by value.

## A slice is a feature

- Every slice is an entry in `harness/feature_list.json` with
  `"part_of": "<parent-name>"`, named `<parent>_<outcome>` (e.g.
  `orders_draft_save`) so entries sort next to their parent.
- Each slice runs the full state machine and both human gates on its own.
  Invariant I1 does the sequencing: slice n+1 starts from what slice n left
  green.
- The parent feature is `in_progress` once its first slice is, and `done`
  only when the last slice's Completion Gate passes.

## Slice spec lite

Per slice, the spec-author writes a **lite trio** — the point of slicing is
that spec effort moves from once-per-feature to per-increment:

- `requirements.md`: 3–6 EARS requirements covering that slice's acceptance
  subset.
- `tasks.md`: 3–5 tasks (batch rules unchanged: 2–4 per dispatch, green on
  their own).
- `design.md`: only when the slice introduces a new decision. Otherwise one
  ADR line in the parent's `design.md` plus a pointer.

## Demo at the Completion Gate

A slice is not done because its tests pass — it is done because **it can be
shown**. The Completion Gate requires a recorded demo: the command (or click
path) and the observed output, end-to-end on the real stack, noted in the
slice's approval record.

**The value test:** if a slice's acceptance cannot be demoed end-to-end, it
is a horizontal layer in disguise — re-cut it.

## Pairing mode

Slices + the hybrid workflow is a pairing setup: one session per slice, the
slice contract approved at the start, the human reviewing diffs
continuously, the recorded demo as the Completion Gate. Gates get lighter
and more frequent — that is the point. The risk hybrid's evidence controls
compensate for is bounded by slice size: a thin slice is cheap to redo.
