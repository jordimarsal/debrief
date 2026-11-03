# Requirements: debrief_role_propose

Slice S3 of parent **debrief** (`part_of: debrief`), gated inside the parent.
One agent question: *what would you change?* — answered by composing both
ports' findings (bench = ggufbench artifacts, run = one buildwright run log)
into a `BW_ROLE_*` diff returned as text. debrief never writes (ADR-0001);
proposals target the role-assignment layer, never the models.yaml registry
(ADR-0003); rows that do not share a task signature are refused, never averaged
(ADR-0004).

Requirement identifiers are inherited from the parent debrief spec: this slice
refines the parent's R1, R2, R5, R6, R7 subset, and IDs stay stable across
parent and slice (no renumbering inside the slice).

## R1
When the agent calls routing.propose, the system shall respond with either a
proposal or a structured error (code, message, detail).

## R2
While the routing.propose tool serves a request, the system shall not write to
any file.

## R5
When the agent calls routing.propose, the system shall compose the bench port's
and the run port's findings into a BW_ROLE_* diff rendered as text.

## R6
The system shall target every proposed change exclusively at BW_ROLE_* role
assignments, never at models.yaml.

## R7
When the bench rows behind a proposal do not share one task signature, the
system shall answer a structured `incomparable_rows` error instead of averaging
or ranking them.

## Traceability

| Requirement | Test(s) | Implementation file(s) | Status |
|-------------|---------|------------------------|--------|
| R1 | | | pending |
| R2 | | | pending |
| R5 | | | pending |
| R6 | | | pending |
| R7 | | | pending |
