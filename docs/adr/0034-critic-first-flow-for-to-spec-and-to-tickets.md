# Critic-first flow for to-spec and to-tickets

Both `to-spec` and `to-tickets` run an adversarial critic review on the drafted artifact **before it is published and before the user reviews the finished artifact**. Critic runs *after* the user's existing product-shaping input, not before it (see "Flow ordering" below). When critic approves, the skill auto-publishes without a manual final-review gate. When critic finds major issues, it automatically revises — the artifact is reviewed up to 3 times (at most 2 automatic revisions) — before publishing.

"Critic-first" is relative to **publishing and final review**, not relative to all user interaction. The existing user gates in each skill are *product-shaping* decisions (what to build, how to slice it) and are **kept, before critic**; critic is a *quality* gate on the shaped artifact; auto-publish removes only the redundant *final-review* gate on an artifact critic has already vetted.

## Flow ordering (exact, per skill)

**to-spec** — the Step 2 seam-check is **kept** (it shapes the spec's Testing Decisions and is a design-shape decision, not a quality decision):

1. Explore repo / read requirements (Step 1).
2. Seam-check with the user (Step 2) — **kept**, product-shaping, before critic.
3. Write the draft spec to a **staging file** with `artifact-type: spec` frontmatter (see ADR-0037); do **not** publish yet (see "Draft staging" below and ADR-0038).
4. Run the critic loop over the draft file (invocation per ADR-0039).
5. On approval → publish (write to tracker, apply `ready-for-agent`); on non-approval → per "Cap exhaustion" below.

**to-tickets** — the Step 4 quiz is **kept** (it is product-shaping — slice granularity and blocking-edge topology are decisions only the user can make, not quality defects critic can resolve):

1. Gather context (Step 1), optional explore (Step 2).
2. Draft vertical slices (Step 3).
3. Quiz the user on granularity and edges until approved (Step 4) — **kept**, product-shaping, before critic.
4. Write the draft ticket files under `draft-issues/` **plus a manifest** with `artifact-type: tickets` frontmatter (see ADR-0037) to the staging directory; do **not** publish yet.
5. Run the critic loop over the manifest (ADR-0039).
6. On approval → publish (Step 5: create issues + blocking edges, apply `ready-for-agent`); on non-approval → per "Cap exhaustion" below.

Auto-publish removes neither user gate; it removes the extra round-trip of asking the user to re-approve an artifact critic has already vetted.

## Headless behaviour at user gates

The two product-shaping gates above (to-spec Step 2 seam-check, to-tickets Step 4 slice quiz) both require an interactive user. But ADR-0035 makes `to-spec` headless-capable, and `to-tickets` may likewise be driven by another agent, so their behaviour when **no interactive user is present** must be defined.

### Headless detection

The skill detects headless mode the same way critic detects plan-mode unavailability: by checking whether the **`AskUserQuestion` tool is available** (tool presence in the system prompt). When `AskUserQuestion` is absent, the skill is headless.

**In headless mode the skill skips the interactive seam-check and slice-quiz gates and proceeds directly to draft + critic.** Headless invocation **implies pre-shaped context**: the calling agent is expected to have already resolved the product-shaping decisions (test seams for a spec; slice granularity and blocking-edge topology for tickets) in the conversation/task description it passes in. The skill draws those decisions from that shaped context instead of quizzing a user.

**Shaping-context validation:** before skipping the seam-check or slice-quiz gate, the skill validates that the conversation/task context contains explicit seam or slice decisions. If no such decisions are found, the skill **stages-and-stops** with the message: "headless mode requires pre-shaped context with seam/slice decisions — provide seam or slice decisions in the task description and re-invoke." The skill does **not** draft from empty context; an empty context in headless mode is an error, not an invitation to guess.

This is deliberately distinct from the *publish* gate: headless mode **skips the shaping gates** (they need a human that isn't there, and the context substitutes for them) but **does not skip the safety of publish-only-on-approval** — cap exhaustion still stages and stops (see "Cap exhaustion and headless behaviour" below). Skipping a shaping question is safe because the context supplies the answer; auto-publishing an unvetted artifact is not.

## Feature-slug derivation

The `<feature-slug>` names the staging directory and is load-bearing for every staging and publish path within a run, so it must be defined and stable for the duration of that run.

- **Interactive / topic-derived:** the slug is derived from the conversation's feature name — taken from the first user message or the task description that motivated the spec/ticket work — then slugified (lowercased, non-alphanumerics collapsed to `-`, trimmed).
- **Headless fallback:** `<session-id>-<timestamp>` (no external argument needed).

The slug lives in memory for the duration of the run. Slug persistence (writing a `slug.txt` file for cross-run resume) is part of the deferred resume subsystem and is scoped to ADR-0041, not here.

## Draft staging

Publishing is **deferred until critic approval**. Before the critic loop, the skill writes the draft to staging under `.scratch/<feature-slug>/`:

- **to-spec**: `.scratch/<feature-slug>/draft-spec.md` (promoted to `.scratch/<feature-slug>/spec.md` on publish).
- **to-tickets**: `.scratch/<feature-slug>/draft-issues/<NN>-<slug>.md` (one draft per ticket) plus `.scratch/<feature-slug>/manifest.md` listing them in dependency order. Draft tickets stage under **`draft-issues/`**, distinct from the published `issues/` directory the local tracker reads.

**Staging-collision behaviour:** if the staging directory already exists when the skill runs (e.g. a re-run after an interrupted session), it **overwrites** draft files — the re-run is a fresh start on the draft, not a resume of a prior run (resume is deferred to ADR-0041). A fresh start also **clears prior-run loop state** left in the staging directory — specifically any `dirty` marker (ADR-0038) and any stale critic-review output — so a marker from an earlier failed run cannot hard-stop an otherwise-clean re-run. The `dirty` hard stop therefore only fires **within** a single run. If published files already exist at the publish destination (`.scratch/<feature-slug>/spec.md` for a spec, or `.scratch/<feature-slug>/issues/<NN>-*.md` for tickets), the skill **aborts** with "already published — delete published files to republish" and does **not** clobber them. This guards against inadvertently overwriting a human-reviewed published artifact.

The staging directory is kept **separate from the live tracker location** so a draft is never mistaken for a published artifact. For the local-file tracker the published location is `.scratch/<feature-slug>/issues/<NN>-<slug>.md`; staging draft tickets in the same `issues/` directory would make staging and publish indistinguishable, so drafts stage under `draft-issues/` and `draft-spec.md` and are **promoted** on publish (see "Publish is manifest-driven" below and ADR-0040).

For a local-file tracker, "publish" promotes these files into place. For a real tracker (GitHub, Linear), the staged files are local drafts and "publish" creates the corresponding issues via the tracker API (ADR-0040). The draft always exists on disk before critic runs, because the critic loop and synthesizer operate on files (ADR-0038).

## Publish is manifest-driven; empty/stale artifact states

Publishing reads the **manifest** (for tickets) or the single staged spec file, never the staging directory listing directly, so stale or orphaned files left by an earlier iteration cannot be published by accident. The manifest is the authoritative list of what to publish and in what order.

- **Zero-slice artifact (abort):** if the tickets manifest lists no ticket files (or the drafting step produced none), publish **aborts** — there is nothing to publish and an empty tracker write is never useful. The skill reports the empty state and stops; it does not create a placeholder issue.
- **Local-tracker promotion steps (on approval):**
  1. **to-spec:** copy `draft-spec.md` → `spec.md`, **stripping the `artifact-type:` frontmatter** (the frontmatter is a critic-routing signal per ADR-0037, not part of the published document), then **remove `draft-spec.md`** — mirroring the `draft-issues/` removal below so both artifact types leave no draft copy beside the published file.
  2. **to-tickets:** for each path in the manifest, promote `draft-issues/<NN>-<slug>.md` → `issues/<NN>-<slug>.md`, apply `ready-for-agent`, then **remove the `draft-issues/` staging directory** so no draft copies linger beside the published issues.
- **Real-tracker publish** follows ADR-0040 (two-phase create-then-link), again driven by the manifest.

## Cap exhaustion and headless behaviour

Auto-publish happens **only** on genuine critic approval (critic's `auto_approval == True`). Any other terminal state — revise-at-cap, major severity, invalid critic output, or hard-abort — leaves the draft staged and unpublished.

- **Interactive** (a human is present): at the iteration cap without approval, show the staged artifact and the unresolved critic issues, then offer **revise / publish anyway / abandon**.
- **Headless** (agent/no interactive user, as `to-spec` becomes per ADR-0035): publishing is a side-effecting, hard-to-undo action, so cap-exhaustion **must not** auto-publish. The skill writes the draft plus the critic review to staging and **stops**, reporting the unresolved issues for a human to decide. Headless publishing occurs only on true approval.

## Considered Options

- **User-first (final review before critic)**: user approves the finished artifact, then critic runs. Rejected — the user reviews an unvetted artifact and critic may then force it to change, wasting that review; only the *product-shaping* user input (seams, slice topology) genuinely needs to precede critic, and that is retained.
- **Remove the user gates entirely**: rejected — the seam-check and the slice quiz are product decisions (test seams, slice granularity, blocking-edge topology) that critic cannot make; silently abolishing them would change the interaction model and produce artifacts shaped by guesses rather than user intent.
- **Hard stop on major**: reject without auto-revise. Rejected — surfaces every major finding to the user for manual fixing, killing the auto-proceed guarantee that motivates this whole design.
- **Publish immediately, critic after**: rejected — a rejected artifact cannot be un-published (issues created in a real tracker are hard to delete, ADR-0040), so vetting must precede the irreversible step.
