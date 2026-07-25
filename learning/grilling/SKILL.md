---
name: grilling
description: Relentless design interview — stress-test any plan by walking every branch of the decision tree.
---

## Interactive grilling phase

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time, waiting for feedback on each question before continuing.

If a question can be answered by exploring the codebase, explore it — search source code conceptually and cross-file, search docs and requirements as a document corpus, and for architecture-level questions start with a global search before reading individual files.

Do not act on the plan until I confirm we have reached a shared understanding.

## Capturing decisions as ADRs

If the plan warrants a durable record, offer to capture the key decisions we reach as Architecture Decision Records (ADRs) — one per significant decision, noting the context, the decision, and its consequences. Use the `/domain-modeling` skill to record ADRs as they are locked in during the interview. Some decisions may be executed immediately; that's fine — just capture them.

## Post-grilling: automatic critic review

When grilling concludes and ADRs have been captured, I will automatically:

1. **Check for ADRs** — look for any `.md` files in `docs/adr/`
2. **Write the manifest** — use the Write tool to write a plan file (in the `plans/` directory) containing a markdown list of ADR file paths (e.g., `- docs/adr/0001-foo.md`), with a preamble explaining these are design decisions reached during grilling
3. **Invoke critic** — call `/critic pickup:<manifest_file_path>`, passing the exact path written in step 2, so critic can locate the manifest without relying on plan-mode context (which may be unavailable in agent / headless runs)

Critic will read the manifest, follow the links to the ADR files, review them, and edit them **directly** during revisions. The ADR files are the ground truth; the manifest is just a pointer list.

Critic's review is **advisory**: it will flag blind spots, contradictions, and edge cases, and return a verdict. You decide whether to iterate or accept the identified risks.
