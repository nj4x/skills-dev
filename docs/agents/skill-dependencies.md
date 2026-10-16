# Cross-skill dependencies

When changing a multi-turn skill, preserve its dependency contracts rather than treating each `SKILL.md` as isolated. The deduplicated dependency graph:

- `planning/critic` → `planning/repeat`: critic loads `repeat/SKILL.md` for the loop contract; falls back to an inlined contract if absent.
- `planning/repeat` → `session/mark`: with no args, `repeat` reads the mark file written by `/mark` to synthesise a task.
- `email/inbox` → `email/mail`: inbox delegates all IMAP access to `mail.py`; its final step can also invoke `publishing/html-view` if installed.
- `learning/grilling` → `planning/critic`: grilling automatically invokes critic at the end to audit ADRs; requires critic to be installed.
- `engineering/grill-with-docs` → `learning/grilling` + `engineering/domain-modeling`: delegates grilling to the grilling skill and doc creation to `/domain-modeling`. Inherits the grilling → critic dependency.
- `engineering/improve-codebase-architecture` → `learning/grilling`: invokes the grilling skill in its deepening loop.
- `engineering/setup-skills` → `dev/writing-for-agents`: when syncing an existing `docs/agents/*.md` file with its seed template, composes the merged text via `Skill("writing-for-agents")`; falls back to a section-by-section merge if absent.
- `engineering/refactor-tests` → `engineering/codebase-design` + `engineering/tdd`: Step 7b reads `codebase-design` for module, interface, seam, adapter, and quotes the seam definition from `engineering/tdd/SKILL.md:20` word for word. Keep the quote and those terms in step when either skill changes.
- `engineering/to-spec` → `engineering/setup-skills`: requires `docs/agents/issue-tracker.md` written by `setup-skills`; prompts the user to run `/setup-skills` if absent.
- `engineering/to-tickets` → `engineering/setup-skills`: same dependency as `to-spec`. When the source is an existing issue, Step 7's real-tracker pass 3 also reads the **Make an issue a sub-issue of a parent** operation, and for its idempotency check the **List the sub-issues of a parent** operation, from that doc (the GitHub seed doc has both). With no such operation (GitLab and other seed docs), or when it fails at runtime, the ticket gets `Part of #<parent>` at the top of its body instead (ADR-0078).
- `engineering/to-tickets` → `engineering/implement`: Step 5 guidance recommends `/implement` for working the ticket frontier one slice at a time.
- `engineering/implement` → `engineering/testing` + `dev/code-review` + `publishing/pr`: runs covering tests via `Skill("testing")`, reviews through a fresh agent that calls `Skill("code-review")` with the brief from `render_review_brief.py`, and writes the PR body with `Skill("pr")`.
- `engineering/implement-spec` → `engineering/to-spec` + `engineering/to-tickets`: requires a published spec and a published task graph before it can run. Local tracker: `.scratch/<feature-slug>/spec.md` and `.scratch/<feature-slug>/issues/*.md`. Real tracker (GitHub, per `docs/agents/issue-tracker.md`): a spec issue and ticket issues linked by native blocking edges. Run `/to-spec` then `/to-tickets` first if either artifact is missing.
- `engineering/implement-spec` → `engineering/implement`: each implementer subagent runs `Skill("implement")` for its ticket, with a commit-only override (no push, no PR).
- `engineering/implement-spec` → `engineering/testing`: the integration Test gate runs `Skill("testing")` on the integration tip before round 1, and the integration fixer re-runs it after each fix.
- `engineering/implement-spec` → `dev/code-review`: the integration reviewer is a fresh `general-purpose` agent that calls `Skill("code-review")` with the brief from `render_review_brief.py`.
- `dev/code-review` → repo standards files: workflow Step 0.5 discovers the target repo's `CODING_STANDARDS.md`, `CONTRIBUTING.md`, coding sections of `AGENTS.md`/`CLAUDE.md`, and `docs/**/standards*` at every effort level, and passes the list to Finder C, the low-effort pass, and the mutating-mode roster and fixes; a repo document wins over the bundled Kotlin, Python, and testing standards. With none found, the bundled standards apply unchanged. Discovery runs inside code-review, so the `implement` review brief carries no standards list.
- `session/handoff`: optionally includes a "suggested skills" section to guide the fresh agent.
