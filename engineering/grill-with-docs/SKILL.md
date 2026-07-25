---
name: grill-with-docs
description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
---

Run a `/grilling` session, using the `/domain-modeling` skill to capture decisions as Architecture Decision Records.

When grilling concludes, `/grilling` will automatically:
- Collect all captured ADRs
- Write a manifest to the plans directory
- Submit them to `/critic` for an adversarial audit of your design decisions

The critic's review is advisory; you decide whether to iterate or proceed with the identified risks.
