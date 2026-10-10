---
lineage-rules: exempt
---

# ADR-0077: Pass --effort Through to code-review in the Review Brief

**Status:** Accepted  
**Date:** 2026-10-09  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet — retrofit tracked in ADR-0065)

## Context

`implement/SKILL.md:20` and `:22` brief a light review and a delta review with effort `low`. `review-brief.md:7` prints `Effort: {{effort}}` into the prompt, but `review-brief.md:11` calls `Skill("code-review", args="--build-cmd ...")` with no `--effort`. So `code-review` runs at its default `high`. `render_review_brief.py:77` accepts only `normal|low`, and `normal` is not a `code-review` value. `code-review/SKILL.md:14` defines `low`, `medium`, and `high`.

## Decision

1. `render_review_brief.py --effort` accepts `high|low`, default `high`. The value `normal` is removed.
2. `review-brief.md:11` passes the value: `Skill("code-review", args="--build-cmd \"{{build_cmd}}\" --effort {{effort}}")`.
3. `low` means a single inline pass. `high` means fan-out plus an adversarial verifier per Critical/Major finding (`code-review/SKILL.md:14`). Light and delta reviews therefore run as single-pass reviews, as `implement/SKILL.md:20` and `:22` intend.
4. Full reviews use the default `high`. Every integration review in ADR-0076 (round 1 and each re-review) also uses `high`. The integration loop has no light or delta reviews, so it never passes `low`. The integration brief passes `--effort high` explicitly, so the value is visible in the brief.

## Considered Options

- Keep default `high` and reword `implement/SKILL.md:20` and `:22` to drop the effort claim: rejected. Light and delta reviews are meant to cost less, and the reword would keep a value the brief prints but never sends.
- Keep `normal` as an alias for `high`: rejected. `normal` is not a `code-review` value, and `high` names the same behavior.

## Consequences

- Light and delta reviews lose the fan-out and the adversarial verifier. A light review still checks each factual claim in changed text against the code it names. A delta review still checks each fix. Verification depth drops for those two review kinds only.
- The finder-verdict rule in `review-brief.md:24` applies only where `code-review` dispatches finders. `low` is a single inline pass (`code-review/SKILL.md:14`), so that rule has no effect under `low`.
- The `Effort:` line printed at `review-brief.md:7` now matches what `code-review` receives.
- Integration reviews in ADR-0076 cost the full `high` fan-out and verifier on every round, so the integration loop's cost is the highest per review. A re-review after a Minor-only fix is a full `high` round too, and it counts toward the 3-round limit in ADR-0076 Decision 5. That limit bounds the total.
