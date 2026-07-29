---
name: data-view-skill
description: Review or migrate legacy DynamoDB Data View companions. For new data realization decisions, use an ADR instead.
disable-model-invocation: true
---

# Legacy Data View Skill

Read `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../../engineering/setup-lineage/SKILL.md#requirements-boundary). New Data View documents are not created or extended. Data shape, persistence representation, provider translation, and query realization belong in the ADR that selects or changes them.

## Legacy review

Use this skill only for an existing Data View companion that needs review or migration.

1. Load the Data View, its `source-srs` document, and each cited `**Source SRS**:` ID.
2. Validate that every Data View element is anchored to its cited SRS requirement. Record uncited or mechanism-bound material as legacy drift; do not add obligations to the companion.
3. When an active change affects data realization, create or amend the governing ADR through `/grill-with-docs`. Put the relevant details in its `## Data Realization` section, including the model, required invariants, and chosen provider translation.
4. Preserve the unchanged legacy Data View. Do not write a replacement companion. Done when every active realization decision is in its ADR and all remaining companion drift is reported.
