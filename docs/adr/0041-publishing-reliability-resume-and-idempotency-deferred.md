# Publishing-reliability: resumable, idempotent-by-slug tracker publish (deferred)

**Status: proposed / deferred.** This ADR carves out the publish **reliability** subsystem that ADR-0040 deliberately descoped, so the critic-first flow (ADR-0034) can ship on stop-and-report semantics without also shipping a resume engine. Nothing here is implemented yet; this records the intended direction so a future implementation does not have to re-derive it.

## Why separate from ADR-0040

ADR-0040 owns two decisions the critic-first flow genuinely needs: the **two-phase create-then-link ordering** and the **stop-and-report** response to partial failure. A full resume subsystem (persisted map, skip-existing, link-pass resume) is logically separable — it changes *how a failed publish recovers*, not *whether the critic-vetted artifact publishes correctly*. Folding it into ADR-0040 would block critic integration on a reliability engine it does not require. It is therefore deferred here.

## Intended design (to be ratified when built)

### Idempotency-by-slug via a write-ahead publish map

- Maintain a persisted **publish map** at `.scratch/<feature-slug>/publish-map.json` recording each ticket's stable **slug** (its staging filename `<NN>-<slug>`) → returned tracker ID.
- **Write-ahead discipline:** append the slug→ID entry *before* (or atomically with) confirming the issue's creation, so a crash in the window between "issue created at the tracker" and "map persisted locally" cannot orphan a created issue from its record. The map is the source of truth for what has been created.
- **Resume the create pass:** re-running publish is **idempotent by slug** — a slug already present in the map is skipped, so only missing issues are created. No duplicates, no idempotency key beyond the slug.

### Link-pass resume idempotency

- After all issues exist, the link pass creates blocking edges. To make it **resumable without duplicating edges**, resume must either **query the tracker for existing edges** or **track created edges locally** (e.g. an `edges` set in the publish map), so re-creating an already-existing link is a no-op / skipped.

### Resume entry point

- Resume reuses the stable `<feature-slug>`, persisted to `.scratch/<feature-slug>/slug.txt` as part of *this* deferred subsystem (ADR-0034 keeps the slug in memory only for the duration of a run), to locate the staging directory, the manifest, and the publish map. The staged artifact plus the publish map are the complete resume state; because publish only runs after critic approval, a failed publish never loses authoring work.

**Inherited constraint to revisit when this ships:** ADR-0034's staging-collision rule currently **overwrites** draft files on a re-run (fresh start, not resume). That is safe only while resume does not exist. When this subsystem is built, "staged artifact + publish map are the complete resume state" and a blind fresh-draft overwrite would destroy half of it. A resume entry must therefore be distinguished from a fresh re-run (e.g. by the presence of `publish-map.json`) and must **not** be preceded by an overwrite. This coupling is recorded here so the future implementation does not silently regress ADR-0034's overwrite semantics.

## Considered Options

- **Never build resume; stop-and-report forever**: acceptable for `to-spec` (single document) but leaves `to-tickets` partial failures as manual cleanup on large ticket sets. Deferred, not rejected — worth building when partial-failure friction is observed.
- **No persisted publish map (retry from scratch)**: duplicates issues without an idempotency key. Rejected as the eventual design; the slug-keyed write-ahead map is the key.
- **Rollback on failure**: destructive and frequently disallowed by tracker permissions (see ADR-0040). Rejected there and here.
