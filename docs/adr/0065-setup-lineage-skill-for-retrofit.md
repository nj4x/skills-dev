# ADR-0065: Setup-Lineage Skill for Retrofitting Existing Repos

**Status**: Approved

**Context**

Existing repositories may have artifacts (FS, SRS, ADRs, specs, tickets) created before lineage rules were established. Retrofitting them manually is tedious and error-prone.

A dedicated skill can automate most of the work and guide the user through gaps.

**Decision**

Create a new **`/setup-lineage`** skill (standalone, not part of setup-skills):

1. **Auto-inference phase** (semantic matching):
   - Scan all FS documents and extract IDs + summaries
   - Scan all SRS documents and extract IDs + summaries
   - For each SRS item, use semantic matching to propose likely FS source(s)
   - Classify proposals into confidence tiers: high (≥85%), medium (50–84%), low (<50%)
   - **No proposals are applied silently.** All writes require explicit user confirmation.
   - High-confidence proposals are pre-checked in a **batch-approval list** presented to the user (one confirmation approves all checked items). The user may uncheck individual items before confirming.
   - Medium-confidence proposals are presented individually for approval
   - Low-confidence or missing matches are flagged for manual grilling in phase 2

2. **Grilling phase** (for gaps):
   - Auto-inference (phase 1) covers only the **FS→SRS** level. For all other chain links — ADR→SRS, spec→ADR, ticket→spec — **no automatic inference is attempted**; grilling-phase manual prompting is the sole mechanism.
   - For SRS items with no proposed FS source, ask: "Which FS requirement does this SRS item trace to?" (Allow: existing ID, create new, or skip)
   - For ADRs with no SRS source, specs with no ADR source, and tickets with no spec source: ask the user to supply the upstream reference directly. (Allow: existing ID/path, create new, or skip)

3. **Writing phase**:
   - Write `lineage-rules` frontmatter to all artifacts
   - Write `**Source X**:` fields to all requirements
   - Generate a lineage report: matched, proposed-unconfirmed, unresolved gaps
   - Flag artifacts with unresolved orphans for manual follow-up

4. **Output**:
   - All artifacts now carry frontmatter and lineage fields
   - Lineage report in `.data/lineage-retrofit-report.md`
   - Unresolved gaps documented for user follow-up

**Consequences**

- Existing repos can adopt lineage incrementally
- Most lineage links are inferred automatically (low friction)
- User is consulted only on ambiguous or missing matches
- Lineage retrofit is a one-time operation; skills maintain it thereafter
- Standalone skill keeps it discoverable and separate from other setup concerns
