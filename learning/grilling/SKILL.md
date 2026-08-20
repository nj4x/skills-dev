---
name: grilling
description: Relentless design interview — stress-test any plan by walking every branch of the decision tree.
arguments: [mode]
---

## Delegated decision-resolution mode

When invoked with `mode` exactly `resolve-decisions`, resolve only the decision set supplied by the calling skill. The caller provides this payload after the mode:

```text
CONTEXT:
<artifact/task context>

DECISIONS:
- ID: <stable decision ID>
  Decision: <decision requiring user input>
  Why: <why it cannot be safely inferred>
  Recommendation: <recommended answer>
```

1. Treat each supplied decision as a node in the design tree. Ask its dependency-ready frontier using the normal `❓ **Q<n>**` format. Do not introduce unrelated design questions.
2. Obtain facts from the available context or tools; do not ask the user to supply facts the environment can answer.
3. After every supplied decision is settled, return exactly:
   ```text
   RESOLVED_DECISIONS:
   - <ID>: <user's answer>
   ```
4. Do **not** offer or write Architecture Decision Records, create a manifest, or invoke `/critic`. Return control to the calling skill.

---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree — settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch an `Explore` sub-agent (`subagent_type: "Explore"`) to find it — don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report — ask the rest of the frontier now. Search source code conceptually and cross-file; search docs and requirements as a document corpus; for architecture-level questions start with a global search before reading individual files. The _decisions_ are the user's — put each to them and wait.

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
