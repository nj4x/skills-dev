---
name: grill-with-docs
description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
disable-model-invocation: true
---

Run a `/grilling` session, using the `/domain-modeling` skill to capture decisions as Architecture Decision Records. Consult `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../setup-lineage/SKILL.md#requirements-boundary): FS/SRS state outcomes and contracts; ADRs record invocation and realization mechanisms.

## Session start

Before the first grilling question, load all SRS documents from `.data/requirements/*-SRS-*.md` into a lookup table of known SRS IDs. Also load every `.data/requirements/**/*.md` whose frontmatter declares `lineage-rules: companion of SRS`; index each companion's cited source SRS IDs and its `source-srs` parent.

## SRS anchor pre-flight (ADR-0059)

FS states high-level product requirements; SRS states the system contracts that satisfy them; ADRs capture lower-level architectural and implementation decisions that realize those contracts. An ADR may therefore trace to a broad existing SRS interface, entity, workflow, or invariant rather than a new one-to-one SRS item. A companion API/Data-View document may locate a cited SRS requirement ID but cannot itself anchor the ADR.

After drafting each ADR, and before writing it to disk, run this pre-flight:

1. Search the SRS corpus and indexed companion documents for the system contract governing the ADR's behavior. Ask: "Which existing SRS requirement does this ADR realize?"
2. If a contract is found, validate its SRS requirement ID against the corpus and use it as the anchor. A companion can supply only an ID it cites; it cannot itself anchor the ADR. Do not create a duplicate SRS requirement solely because the ADR fixes a concrete schema, dependency, validation method, storage representation, or provider translation.
3. If no SRS requirement ID covers the behavior, offer "Create a new SRS requirement now?"
   - Before drafting it, verify the requirement has an FS product outcome or constraint. If not, offer to define the missing FS requirement first.
   - Draft approved new FS/SRS requirements in EARS format, write them to the appropriate documents, and add their IDs to the lookup table.
   - If the user declines, block ADR finalization — the ADR is unanchored.
4. Populate the `**Source SRS**:` field in the ADR body with every validated SRS requirement ID. Done when every validated anchor is listed.

ADR frontmatter must include `artifact-type: adr` and `lineage-rules` per ADR-0056 (see [ADR-FORMAT.md](../domain-modeling/ADR-FORMAT.md)).

## Grilling conclusion

When grilling concludes, `/grilling` automatically collects all captured ADRs, writes a manifest to the plans directory, and submits them to `/critic` for an adversarial audit.
