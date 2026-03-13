# Beads Review: m20-rosnav-migration

**Generated:** 2026-03-13
**Reviewers:** Forward (plan→beads), Reverse (beads→plan), Dependencies (graph integrity)

---

## Summary

| Category | P0 | P1 | P2 | Total |
|----------|----|----|----|----|
| Coverage Gaps | 0 | 0 | 1 | 1 |
| Conversion Scope Creep | 0 | 0 | 0 | 0 |
| Dependency Errors | 0 | 0 | 0 | 0 |
| Content Fidelity | 0 | 0 | 2 | 2 |
| **Total** | **0** | **0** | **3** | **3** |

**Verdict: PASS** — All 3 findings are P2 (advisory only). No fixes required before delivery.

---

## Reviewer Cross-Reference Notes

### Dependency Review: 5 Findings Invalidated

The dependency reviewer reported 5 issues, but cross-referencing against the actual beads
snapshot shows **all 5 are incorrect** — the reviewer misread the snapshot:

| Finding | Reviewer Claim | Actual State | Verdict |
|---------|---------------|--------------|---------|
| False blocker 2.1→2.4 | "2.4 blocked by 2.1" | 2.4 (di-daa85u.8.4) depends on 1.4 only, no 2.1 dep | INVALID |
| False blocker 2.4→2.5 | "2.5 blocked by 2.4" | 2.5 (di-daa85u.8.5) has no dependencies, blocks 4.3 | INVALID |
| Missing blocker Phase 2→4.3 | "4.3 only blocks on 4.1, 4.2" | 4.3 depends on 4.2 AND 2.5 (Phase 2 covered) | INVALID |
| Missing blocker 1.1→3.2 | "3.2 missing dep on 1.1" | 3.2 (di-daa85u.9.2) explicitly depends on 1.1 (di-daa85u.7.1) | INVALID |
| Missing blocker 3.2→4.1 | "4.1 missing dep on 3.2" | 4.1 (di-daa85u.10.1) depends on BOTH 3.1 and 3.2 | INVALID |

### Clarity Review: 6 of 9 Findings Already Fixed

The clarity reviewer evaluated descriptions before Stage 1 fixes were applied.
Cross-referencing against the current bead descriptions:

| Finding | Status |
|---------|--------|
| drdds Humble gap (2.1) | FIXED — bead says "build inside nav container then copy artifacts" |
| Rollback contradiction (2.2 vs 2.4) | FIXED — bead says "rollback via git checkout", no legacy flag |
| Entrypoint caller chain (2.3) | FIXED — bead says "runs inside the nav container (invoked by DockerModule)" |
| AC wildcard import (1.4) | FIXED — bead uses ast.parse instead |
| Stop mechanism (2.5) | FIXED — bead says "pgrep -f launch_nos.py then SIGTERM" |
| DDS discovery mode (3.2) | FIXED — bead says "Use initialPeersList with only AOS unicast" |

---

## P2 Findings (Consider)

### 1. Velocity watchdog not in any acceptance criterion

- **Category:** Coverage Gap
- **Found by:** Forward
- **What:** The plan's Error Handling section notes the M20 motion controller has a 500ms velocity watchdog that stops the robot if no commands arrive. No bead acceptance criterion explicitly verifies this works. Since the watchdog is an existing mechanism (not new work), no new bead is needed — but Task 4.3 could optionally reference it.
- **Fix suggestion:** Optionally add to Task 4.3 AC: "Verify robot stops within 1s of NavCmd ceasing"

### 2. Blueprint remapping guidance is vague

- **Category:** Content Fidelity
- **Found by:** Clarity
- **What:** Task 1.2 says "Use `.remappings()` if stream name conflicts arise" but doesn't explain what a conflict looks like or show example syntax. An implementer hitting an autoconnect error wouldn't know whether to use remappings or look elsewhere.
- **Fix suggestion:** Optionally add to 1.2 description: "If autoconnect raises 'multiple producers for stream X', call `.remappings({'old_name': 'new_name'})` on the affected module"

### 3. FASTLIO2 "initializes" is underspecified in ACs

- **Category:** Content Fidelity
- **Found by:** Clarity
- **What:** Tasks 3.1 and 4.2 say "FASTLIO2 initializes" without defining what observable proves initialization. Task 4.2 does mention checking `docker logs` for 'FAST-LIO is activated' in its description, which partially addresses this.
- **Fix suggestion:** No change needed — Task 4.2 description already specifies the log check. The AC implicitly references the description.

---

## Parallelism Report

- **Dependency waves:** 6
- **Maximum parallel width:** 10 beads (Wave 1)
- **Critical path:** 7 beads: `1.1 → 1.2 → 1.4 → 2.4` then `3.1+3.2 → 4.1 → 4.2 → 4.3`
- **Ready queue:** 10 beads ready immediately

### Dependency Waves

| Wave | Beads | Count |
|------|-------|-------|
| 1 | 0.1, 0.2, 0.3, 0.4, 1.1, 2.1, 2.2, 2.3, 2.5, 3.1 | 10 |
| 2 | 1.2, 3.2 | 2 |
| 3 | 1.3, 1.4 | 2 |
| 4 | 2.4, 4.1 | 2 |
| 5 | 4.2 | 1 |
| 6 | 4.3 | 1 |

---

## Coverage Summary

**Forward (Plan→Beads):**
- Fully matched: 18 tasks
- Partially matched: 0 tasks
- No matching bead: 0 tasks
- Coverage: 100%

**Reverse (Beads→Plan):**
- Plan-backed: 18 tasks
- Structural (phase epics): 5 sub-epics + 1 root epic
- Scope creep: 0
- Gold-plating: 0

**Dependencies:**
- Correctly constrained: 10 dependencies
- Missing blockers: 0
- Over-constrained: 0
- Circular dependencies: 0
