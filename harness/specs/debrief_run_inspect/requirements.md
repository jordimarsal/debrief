# Requirements: debrief_run_inspect

Slice S2 of parent **debrief** (`part_of: debrief`), gated inside the parent.
One agent question: *where did this run break?* — answered from one buildwright
run log and nothing else.

Requirement identifiers are inherited from the parent debrief spec: this slice
refines the parent's R1, R2, R4 subset, and IDs stay stable across parent and
slice (no renumbering inside the slice).

## R1
When the agent calls run.inspect, the system shall respond with either findings
or a structured error (code, message, detail).

## R2
While the run.inspect tool serves a request, the system shall not write to any
file.

## R4
When the agent calls run.inspect, the system shall return findings derived only
from the buildwright run log at the requested path.

## Traceability

| Requirement | Test(s) | Implementation file(s) | Status |
|-------------|---------|------------------------|--------|
| R1 | | | pending |
| R2 | | | pending |
| R4 | | | pending |
