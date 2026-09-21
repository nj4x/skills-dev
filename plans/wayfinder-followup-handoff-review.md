# Wayfinder followup handoff — critic review manifest

Review target: changes to the `wayfinder` skill that add automatic followup capture and handoff when a decision map's frontier empties. Committed as `7a71050`.

## Artifacts to review

- `skills/engineering/wayfinder/SKILL.md` — the changed skill. Review the new "Handoff at frontier empty" section and the edits to steps 4 and 5 of "Work through the map".
- `docs/research/wayfinder-followup-capture.md` — the research that motivated the change, including the four design options considered (A–D) and the original recommendation.
- `/Users/roman/projects/pro-trading/docs/map-144-todo.md` — the manually written artifact whose existence is the evidence of the gap being fixed. The change should make this file unnecessary next time.

## Diff under review

```
git show 7a71050 -- skills/engineering/wayfinder/SKILL.md
```

## Problem being solved

A wayfinder map in the pro-trading repo (issue #144) resolved all its decision tickets. The implementation work those decisions implied was never captured in any tracked form — it survived only in the user's working memory, and had to be reconstructed by hand into `map-144-todo.md` (119 lines of ordered `/implement` and `/to-tickets` invocations). Wayfinder had no terminal step: `SKILL.md` described how to resolve tickets but never what happens when the last one closes.

## Design decisions reached during grilling

These were settled with the user before implementation. The critic should stress-test them, not assume they are correct.

1. **Handoff fires automatically** when the frontier empties — no confirmation prompt. Rejected alternatives: prompt every time; opt-in via a flag in the map's Notes.
2. **Followups are marked with inline tags** in resolution comments — `[impl]`, `[map]`, `[defer]`. Rejected alternative: structured `## Followups` subsections per destination.
3. **Implementation items route to `to-tickets`** via a synthesized spec at `.scratch/<map-slug>/implementation-spec.md`. This exists because `to-tickets` requires a lineage anchor (a spec file or a confirmed ADR path) at staging time, and a wayfinder map is a tracker issue — neither of those.
4. **A successor execution map** is created to track the carried work to completion, inheriting the parent's destination.
5. **Execution maps are terminal** — when a successor's frontier empties it reports done and never spawns another. This exists to stop infinite regress, since shipping work always surfaces more work.
6. **Items explicitly marked "own effort"** spawn their own independent map rather than folding into the successor. This mirrors what map-144-todo item 10 (admin web UI) already says out loud.
7. **Step 5 is strengthened** to require that findings surfaced during resolution become actual tickets or are explicitly parked in `Not yet specified` / `Out of scope` — never left in a resolution comment alone.

## Specific concerns to probe

- **"Plan, don't do" tension.** `SKILL.md:13` states wayfinder produces decisions, not deliverables. A successor execution map carries implementation work. The escape hatch at `SKILL.md:13` permits an effort to override this in its Notes — is leaning on that hatch legitimate here, or is the successor map a to-tickets output wearing a map costume? Wayfinder's four ticket types (`research`, `prototype`, `grilling`, `task`) have no "implement this" type.
- **Destination inheritance.** A map's destination fixes its scope and is what fog gathers toward (`SKILL.md:9`, `:101`). The grilling settled on deriving a new destination and confirming it with the user, but the committed text says the successor inherits the parent's destination verbatim. That is a divergence between what was agreed and what shipped — assess whether it matters.
- **Overlap between routes 3 and 4.** If `[impl]` items are published by `to-tickets` *and* a successor execution map is created, which one owns those tickets? The committed text says the successor's frontier is "the published implementation tickets from step 3" but also says to "wire the implementation tickets as child issues if they don't already exist as a set". Is the ownership unambiguous?
- **Automatic firing and parked maps.** Q1 settled on unconditional firing. If a user parks a map mid-effort with the frontier transiently empty (every open ticket claimed or blocked), does the handoff fire prematurely? Check whether the frontier-empty definition actually distinguishes "done" from "temporarily nothing takeable".
- **Tag discoverability.** The `[impl]` / `[map]` / `[defer]` convention is documented only in the new Handoff section, but it must be applied during step 4 of resolution — earlier in the document and in a different session. Will an agent resolving a ticket know to apply tags?
- **Retroactive scan cost.** The handoff scans "all closed decision tickets" for tags. On a large map this is many issue fetches in the session that happens to close the last ticket. Is that bounded?
- **Concurrency.** `SKILL.md` warns that parallel sessions edit the tracker concurrently. Two sessions closing the last two tickets near-simultaneously could both observe an empty frontier and both fire the handoff, creating duplicate successor maps.
