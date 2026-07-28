---
name: grill-with-docs
description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
disable-model-invocation: true
---

Run a `/grilling` session, using the `/domain-modeling` skill to capture decisions as Architecture Decision Records.

## Session start

Before the first grilling question, load all SRS documents from `.data/requirements/*-SRS-*.md` into a lookup table of known SRS IDs. This table is used by the SRS anchor pre-flight (below) throughout the session.

## SRS anchor pre-flight (ADR-0059)

After drafting each ADR, and before writing it to disk, run this pre-flight:

1. Ask: "Which SRS requirement(s) does this ADR satisfy?"
2. Validate each named SRS ID against the lookup table:
   - **Found**: proceed
   - **Not found**: offer "Create new SRS requirement(s) now?"
     - **Yes**: draft the missing SRS item(s) in EARS format, get user approval, write to the appropriate SRS document, and add the new IDs to the lookup table
     - **No**: **block ADR finalization** — an unanchored ADR is invalid; do not write the ADR file
3. Populate a `**Source SRS**:` field in the ADR body with all validated IDs before writing.

ADR frontmatter must include `artifact-type: adr` and `lineage-rules` per ADR-0056 (see [ADR-FORMAT.md](../domain-modeling/ADR-FORMAT.md)).

## Grilling conclusion

When grilling concludes, `/grilling` will automatically:
- Collect all captured ADRs
- Write a manifest to the plans directory
- Submit them to `/critic` for an adversarial audit of your design decisions

The critic's review is advisory; you decide whether to iterate or proceed with the identified risks.
