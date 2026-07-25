# Cross-skill dependencies

When changing a multi-turn skill, preserve its dependency contracts rather than treating each `SKILL.md` as isolated. The deduplicated dependency graph:

- `planning/critic` → `planning/repeat`: critic loads `repeat/SKILL.md` for the loop contract; falls back to an inlined contract if absent.
- `planning/repeat` → `session/mark`: with no args, `repeat` reads the mark file written by `/mark` to synthesise a task.
- `email/inbox` → `email/mail`: inbox delegates all IMAP access to `mail.py`; its final step can also invoke `publishing/html-view` if installed.
- `learning/grilling` → `planning/critic`: grilling automatically invokes critic at the end to audit ADRs; requires critic to be installed.
- `engineering/grill-with-docs` → `learning/grilling` + `engineering/domain-modeling`: delegates grilling to the grilling skill and doc creation to `/domain-modeling`. Inherits the grilling → critic dependency.
- `engineering/improve-codebase-architecture` → `learning/grilling`: invokes the grilling skill in its deepening loop.
- `engineering/to-spec` → `engineering/setup-skills`: requires `docs/agents/issue-tracker.md` written by `setup-skills`; prompts the user to run `/setup-skills` if absent.
- `engineering/to-tickets` → `engineering/setup-skills`: same dependency as `to-spec`.
- `engineering/to-tickets` → `engineering/implement`: Step 5 guidance recommends `/implement` for working the ticket frontier one slice at a time.
- `session/handoff`: optionally includes a "suggested skills" section to guide the fresh agent.
