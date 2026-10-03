# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root, or
- **`GLOSSARY-MAP.md`** at the repo root if it exists — it points at one `GLOSSARY.md` per context. Read each one relevant to the topic.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in. In multi-context repos, also check `src/<context>/docs/adr/` for context-scoped decisions.
- **`.data/requirements/`** at the repo root — formal requirements docs (FS, SRS, API definitions, test cases). Read docs relevant to the feature you're working on.
- **`.data/docs/`** at the repo root — external reference documentation (vendor APIs, third-party integrations). Skills in `.data/docs/skills/` may provide additional tools.

If any of these files or directories don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill creates `GLOSSARY.md` and ADRs lazily when terms or decisions actually get resolved.

## File structure

Single-context repo (most repos):

```
/
├── GLOSSARY.md
├── .data/
│   ├── requirements/     ← formal requirements docs (FS, SRS, API definitions)
│   └── docs/             ← external reference docs (vendor APIs, integrations)
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

Multi-context repo (presence of `GLOSSARY-MAP.md` at the root):

```
/
├── GLOSSARY-MAP.md
├── .data/
│   ├── requirements/
│   └── docs/
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── GLOSSARY.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── GLOSSARY.md
        └── docs/adr/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_

## Search concepts

**Conceptual search**: Search source code cross-file by domain concept, not literal string; search requirements and design documents as document wholes, not individual words. Used when symbol-level or keyword search would over-match or miss the target entirely (e.g., finding all uses of an abstract pattern without searching for the pattern's name).

## Requirements ID conventions

Formal requirements carry stable IDs (e.g. `REQ-1234`) assigned by `/FS-skill` and `/SRS-skill`. When downstream work traces to a requirement, carry the ID forward two ways:

- **`Requirements:` field** — a labelled line on tickets and ADRs listing the IDs the artifact satisfies (e.g. `Requirements: REQ-1234, REQ-1240`).
- **Inline `(ID)` tags** — parenthetical IDs on individual spec items (user stories, implementation decisions) that trace to a requirement.

`GLOSSARY.md` never carries requirement IDs — it stays a pure glossary of names and definitions. IDs live in specs, tickets, ADRs, and commit/PR bodies.
