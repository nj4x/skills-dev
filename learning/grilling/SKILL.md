---
name: grilling
description: Relentless design interview — stress-test any plan by walking every branch of the decision tree.
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Each question should be formatted like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree — settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it — don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report — ask the rest of the frontier now. Search source code conceptually and cross-file; search docs and requirements as a document corpus; for architecture-level questions start with a global search before reading individual files. The _decisions_ are the user's — put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.

## Capturing decisions as ADRs

If the plan warrants a durable record, offer to capture the key decisions we reach as Architecture Decision Records (ADRs) — one per significant decision, noting the context, the decision, and its consequences. Use the `/domain-modeling` skill to record ADRs as they are locked in during the interview. Some decisions may be executed immediately; that's fine — just capture them.

## Post-grilling: automatic critic review

When grilling concludes and ADRs have been captured, I will automatically:

1. **Check for ADRs** — look for any `.md` files in `docs/adr/`
2. **Write the manifest** — use the Write tool to write a plan file (in the `plans/` directory) containing a markdown list of ADR file paths (e.g., `- docs/adr/0001-foo.md`), with a preamble explaining these are design decisions reached during grilling
3. **Invoke critic** — call `/critic pickup:<manifest_file_path>`, passing the exact path written in step 2, so critic can locate the manifest without relying on plan-mode context (which may be unavailable in agent / headless runs)

Critic will read the manifest, follow the links to the ADR files, review them, and edit them **directly** during revisions. The ADR files are the ground truth; the manifest is just a pointer list.

Critic's review is **advisory**: it will flag blind spots, contradictions, and edge cases, and return a verdict. You decide whether to iterate or accept the identified risks.
