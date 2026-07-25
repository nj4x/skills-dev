# Critic reviews refactored output plus the original, not ADRs

At the end of the refactoring skill, critic is invoked to audit the refactored CLAUDE.md and satellite files. Crucially, the manifest handed to critic includes **both the refactored output and the pre-refactor original** (or a computed diff of what was removed, moved, and re-categorized), not the output alone. The manifest points to these files rather than to a set of ADRs about the design process.

## Why the original must be in the manifest

Auditing the output alone cannot detect over-deletion or miscategorization: once redundant instructions are deleted, they are gone, so critic examining only the post-deletion files has no way to know something valuable was dropped. To assess over-deletion, mis-splitting, and poorly scoped essentials, critic needs a reference point. The skill therefore provides critic with:

- the refactored root CLAUDE.md and all satellite files, and
- the **pre-refactor original** CLAUDE.md (conveniently, the timestamped backup from ADR-0027 serves as this reference), and
- a **diff/mapping** of every instruction's disposition — kept-as-essential, moved-to-satellite-X, or deleted-as-redundant.

With the original and the disposition map, critic can verify that deleted content was genuinely redundant, that moved instructions landed in the right category, and that essentials were neither over- nor under-scoped.

## Considered Options

In the standard grill-with-docs flow, critic reviews ADRs capturing design decisions. That was skipped here because the refactoring skill produces no decision ADRs — the refactored output files *are* the record of decisions (what was kept, what was split, what was deleted). Having critic review design-process ADRs rather than the output would miss the most common failure modes: miscategorized instructions, over-deleted content, poorly scoped essentials.

An earlier version of this decision pointed critic at the output files *only*. That was rejected: it claimed critic would catch over-deleted content, but with the deleted content already gone, critic had no evidence of what was removed. Including the original (backup) and the disposition diff closes that gap.

## Consequences

Critic must be capable of auditing prose CLAUDE.md files (not just code or structured specs) and of comparing an original against a refactored result via the supplied diff. The manifest written by the skill includes a preamble explaining that critic's job is to assess whether the refactored structure is correct — right essentials, right categories, no valuable content lost — using the original and disposition map, not to evaluate process decisions. The skill depends on ADR-0027's timestamped backup existing so the original is always available to critic.
