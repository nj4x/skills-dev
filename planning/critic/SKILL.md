---
name: critic
description: Iteratively build an implementation plan and refine it with an adversarial critic until approved. Use when planning a feature, designing an implementation, or critically reviewing a design. Pass no arguments to pick up the currently active plan and run the critic against it.
arguments: [task, max_iterations, mode]
argument-hint: "[task] [max-iterations] [auto]"
---

<!-- Note: `arguments` is supported by the Claude Code CLI. The VS Code agent-linter warning is cosmetic and accepted. -->

You are running a plan/critic loop for this task:

TASK: $task
MAX_ITERATIONS: $max_iterations
MODE: $mode (default: guided)

---

## Step 0 — Load repeat contract

Check whether `~/.claude/skills/repeat/SKILL.md` exists:
```bash
test -f ~/.claude/skills/repeat/SKILL.md && echo FOUND || echo MISSING
```

- **FOUND**: Read `~/.claude/skills/repeat/SKILL.md` and follow the repeat loop contract defined there, binding the extension points below (GENERATE_STEP, REVIEW_STEP, FINALIZE_STEP). The repeat contract governs Guards, Mode detection, Decision Protocol, and the loop — do not re-derive them here.
- **MISSING**: stop with: `repeat skill not found. Install it with: ln -s /Users/roman/projects/skills-dev/planning/repeat ~/.claude/skills/repeat`

In both cases, apply the critic-specific overrides and extension point bindings below before starting.

---

## Critic-specific overrides

Critic-specific deltas on top of the repeat contract:

- **PICKUP trigger**: TASK is empty or the literal placeholder `$task` or `$1`. Resolve the active artifact via this order:
  1. **Explicit path sentinel** — if TASK begins with `pickup:`, strip the prefix to obtain `<path>`, read that file with the Read tool, and store `<path>` as `plan_file_path`. Skip plan-mode context line lookup entirely. This is the **plan-mode-independent** path and is required in environments where plan mode is disabled (agent / headless runs).
  2. **Plan-mode context line** `A plan file exists from plan mode at: <path>` — used only when plan mode is available and active (interactive Claude Code). Store the path as `plan_file_path`.
  3. Hard-stop: `No active plan found. Pass an explicit path via pickup:<path>, re-run /critic "<task>" to generate one, or enter plan mode with an existing plan first.`

### Loop state and critic ledger

After REVIEW_STEP resolves `artifact_type` and its artifact path on iteration 0, and before invoking the coordinator, derive `staging_dir` as the parent directory of `spec_file_path` or `manifest_path` for `spec` and `tickets`; for `plan` and `design-review`, derive it as the parent directory of `plan_file_path` (for a fresh headless plan, first derive `plan_file_path` as `~/.claude/plans/<CLAUDE_CODE_SESSION_ID>-plan.md`). Set `critic_ledger_path = <staging_dir>/critic-ledger.json`.

Initialize the file to `[]` only when it does not already exist. After each REVIEW_STEP, upsert each severity-prefixed issue into it using this record shape:
```json
{ "id": "ID-001", "group": "A", "claim": "...", "evidence": "...", "severity": "major", "fix": "...", "status": "open", "introduced_pass": null }
```
Assign new IDs sequentially. Match repeats by ID when present, otherwise by normalized claim text; update evidence and severity. Mark an existing issue `fixed` only when a later REVIEW_STEP no longer returns its claim. Never write the ledger after GENERATE_STEP. In guided mode, ask the user before marking an issue `accepted`; in auto mode, never mark an issue accepted.

Maintain `major_count_in_ledger` after every REVIEW_STEP. On pass 2+, set `halt_convergence_guard = true` when the current count of open major issues is greater than or equal to the previous pass's count. Bind this value into repeat's STOP_CONDITIONS as described below.

---

## Step 1 — Session setup

**1a.** Use Bash: `echo $CLAUDE_CODE_SESSION_ID`. Store for display only.

**1b.** Print:
```
Plan/critic sessions
  orchestrator  <CLAUDE_CODE_SESSION_ID>
  planner       (agent)   pending
```

**1c.** Determine `critic_model` and `critic_effort` from the orchestrator's own model (stated in the system prompt, e.g., "powered by the model named Sonnet 4.6"):

| Orchestrator / planner tier | `critic_model` | `critic_effort` |
|---|---|---|
| haiku (model name contains "haiku") | `"sonnet"` | normal |
| sonnet (model name contains "sonnet") | `"opus"` | normal |
| opus (model name contains "opus") | `"opus"` | **higher** |

When `critic_effort` is **higher** (opus→opus case), prepend to the critic prompt:
`Think step by step and reason at maximum depth before producing your JSON verdict.`
followed by a blank line.

---

## Extension point bindings

### GENERATE_STEP — Planner agent

**Print status:**
- `iteration == 0`, PICKUP: `  planner   (agent)   skipped (using active plan)`
- `iteration == 0`, FRESH: `  planner   (agent)   running (iteration 1)`
- `iteration > 0`: `  planner   (agent)   running (revision, iteration <iteration+1>)`

**Initial plan** (`iteration == 0`, FRESH):

Invoke the Agent tool with:
- `subagent_type: "claude"`
- `description: "Generate implementation plan"`
- `prompt`:
  ```
  You are a software implementation planner. Write a complete, concrete implementation plan for the following task.
  Be specific: list files to change, key decisions, risks, and open questions.
  You may use the Agent tool to spawn sub-agents for major parallel research tasks if useful, but MUST return a single coherent plan text as your final output.
  Return ONLY the plan text — no preamble, no closing remarks.
  [If MODE != auto]: After the plan text, if any decisions depend on architecture choices,
  metadata/schema field names or semantics, external-integration patterns (API contracts,
  auth, message formats), or cannot be verified from available context, append on its own line:
  FLAGGED_DECISIONS: [{"decision": "<what you assumed>", "why_flagged": "<architecture/schema/integration concern>"}]
  Omit the block entirely if no decisions need flagging.

  TASK:
  [exact $task text, verbatim]
  ```

**Revision** (`iteration > 0`):

Invoke the Agent tool with:
- `subagent_type: "claude"`
- `description: "Revise [implementation plan|design decisions] based on critic feedback"`
- `prompt`:
  ```
  [IF is_design_review]
  You are a design decision critic's assistant. Revise the ADR files to address the critic's feedback on your design decisions.

  **IMPORTANT**: You have Write and Edit tool access. For each ADR file listed in the manifest, read it, apply the fixes suggested by the critic, and **edit the file in place** using the Edit tool. Do NOT attempt to return revised file content in text — the files are your artifact.
  You may use the Agent tool to spawn sub-agents for major parallel revision tasks if useful, but MUST return a single coherent manifest text as your final output.

  After editing the ADR files, return ONLY the manifest text — no preamble, no closing remarks. The manifest should still list all the same ADR file paths (unchanged), because the actual revisions are in the files you just edited.
  [ELSE IF artifact_type == spec]
  You are a spec writer's assistant. Revise the staged spec file to address the critic's feedback.

  **IMPORTANT**: You have Write and Edit tool access. Read the spec at `<spec_file_path>`. Retain the `artifact-type: spec` frontmatter block at the top of the file — it must not be removed. Apply the critic's fixes by editing the file in place using the Edit tool. Do NOT return revised spec text in your response.

  Return the spec file path as the first line. Then emit zero or more `INTRODUCED: [name]` lines for constructs introduced in this revision; no other output.
  [ELSE IF artifact_type == tickets]
  You are a ticket author's assistant. Revise the staged ticket files and manifest to address the critic's feedback.

  **IMPORTANT**: You have Write and Edit tool access. Read the manifest at `<manifest_path>` and all ticket files it references. Edit them in place. You may change content within a ticket file (edit that file), add a slice (write a new ticket file and append its path to the manifest in dependency order), or remove/renumber a slice (delete/rename the ticket file, update the manifest, and update every sibling `Blocked by` reference that pointed at the changed slug so no dangling edges remain).

  After all edits, run post-edit validation and assert: (a) every manifest path refers to an existing, readable file; (b) every `Blocked by` reference in every ticket resolves to a slug present in the manifest; (c) no staged ticket file is absent from the manifest; (d) the `Blocked by` graph is acyclic and no ticket blocks itself. If any assertion fails, write a `dirty` marker file at `.scratch/.../dirty` (derive staging dir as the parent directory of the manifest), report the specific inconsistency, and stop rather than returning.

  Return the manifest file path as the first line. Then emit zero or more `INTRODUCED: [name]` lines for constructs introduced in this revision; no other output.
  [ELSE]
  You are a software implementation planner. Revise the current plan to address the critic's feedback.
  You may use the Agent tool to spawn sub-agents for major parallel revision tasks if useful, but MUST return a single coherent revised plan text as your final output.
  Return ONLY the revised plan text — no preamble, no closing remarks.
  [END IF]

  [If MODE != auto]: Append FLAGGED_DECISIONS for any new assumption-bearing decisions introduced by this revision.
  [If user_answers is non-empty]: Also incorporate these user answers to previously flagged decisions:
  [insert user_answers as markdown bullets]

  TASK:
  [exact $task text, verbatim]

  [IF is_design_review]
  MANIFEST (ADR file paths):
  [insert plan_or_manifest verbatim]

  CURRENT ADR FILES (content):
  [insert adr_content verbatim]
  [ELSE IF artifact_type == spec]
  STAGED SPEC PATH:
  [insert spec_file_path verbatim]

  (Read the spec body from this path using the Read tool before editing.)
  [ELSE IF artifact_type == tickets]
  MANIFEST PATH:
  [insert manifest_path verbatim]

  (Read the manifest and all referenced ticket files from their paths using the Read tool before editing.)
  [ELSE]
  CURRENT PLAN:
  [insert current_plan verbatim]
  [END IF]

  LEDGER SUMMARY (open issues from prior passes):
  [insert each open major ledger record as: "- <id> (group <group>, severity major): <claim> → still open", or "- none"]

  CRITIC TOP ISSUES:
  Only major-severity issues are listed below. Minor improvements may be addressed in future passes if they accumulate.
  [insert each `last_top_issues` item whose `[severity]` prefix is `[major]` as "- <item>"]

  SUGGESTED FIXES:
  [insert suggested fixes that correspond to the listed major issues only]

  If you introduce new functions, classes, configuration keys, or machinery, append one line per construct: `INTRODUCED: [name]`. For `spec` and `tickets`, emit these only after the required path on the first line. For plan and design-review, append them after the artifact or manifest.
  Note: the [design|plan] will not be approved until all major issues are resolved. Minor improvements may still be noted on approval.
  ```

**Post-GENERATE_STEP (guided mode, i.e. when MODE != auto):** 

For design review (`is_design_review == true`): the agent has edited ADR files in place. The `artifact_text` is just the manifest (ADR file paths). Store it as-is; no need to extract revised content since it's already in the files.

For `artifact_type == spec`: extract `INTRODUCED:` lines, then take the first remaining non-empty line as the returned path. Verify it matches `spec_file_path` and the file exists and is non-empty; if not, write the `dirty` marker (`.scratch/.../dirty` — staging dir = parent of `spec_file_path`) and hard-abort. Store that path as `artifact_text` — the review content will be re-read from `spec_file_path` in the next REVIEW_STEP.

For `artifact_type == tickets`: extract `INTRODUCED:` lines, then take the first remaining non-empty line as the returned path. Verify the manifest file exists; if not, hard-abort. Store that path as `artifact_text` — the manifest and all ticket bodies will be re-assembled in the next REVIEW_STEP.

For plan review: extract and strip the `FLAGGED_DECISIONS` block from the agent text using this deterministic rule: the block is the last line (and everything from it to EOF) whose text begins with the literal `FLAGGED_DECISIONS:`. Strip that suffix from `artifact_text` before storing it.

For every artifact type, extract each `INTRODUCED: [name]` annotation from the revision response before path validation or storing `artifact_text`. Add the construct name to the ledger with `introduced_pass = iteration + 1`; retain the annotation in an edited artifact only when it is semantically appropriate to that artifact.

Parse the stripped JSON using the same temp-file harness as REVIEW_STEP:
```bash
tmpfile_fd="$(mktemp -u /tmp/pwc_flagged.XXXXXX)"
```
Write only the JSON array after the colon to `$tmpfile_fd` using the Write tool, then validate:
```bash
FD_TMPFILE="$tmpfile_fd" python3 - <<'PYEOF'
import json, sys, os
with open(os.environ['FD_TMPFILE']) as f:
    raw = f.read().strip()
try:
    data = json.loads(raw)
    assert isinstance(data, list), "expected array"
    for item in data:
        assert 'decision' in item and 'why_flagged' in item, f"missing key in {item}"
except (json.JSONDecodeError, AssertionError) as e:
    print(f"FLAGGED_DECISIONS_PARSE_ERROR: {e}", file=sys.stderr)
    sys.exit(1)
print(json.dumps(data))
PYEOF
```
On non-zero exit: `rm -f "$tmpfile_fd"`, then hard abort: `FLAGGED_DECISIONS parse failed at iteration <iteration+1>: <stderr content>`.
On success: `rm -f "$tmpfile_fd"`. If line not present or array is empty, `flagged_decisions = []`.

If `flagged_decisions` is non-empty, the **orchestrator** calls `AskUserQuestion` for each entry (one question per entry, include `why_flagged` as context). Collect answers as `user_answers` for the next revision prompt.

**Hard abort conditions:**
- Agent call fails → "Planner agent failed at iteration `<iteration+1>`."
- Returned text (after stripping FLAGGED_DECISIONS) is empty → "Planner agent returned empty plan at iteration `<iteration+1>`."

---

### REVIEW_STEP — Adversarial critic agent

Print: `  critic #<iteration+1>   (agent)   running`

**Detect artifact type and resolve file references:**

Before invoking the agent:

1. **Resolve `artifact_type`** — **on iteration 0 only**. Persist the resolved value as loop state and reuse it unchanged on all subsequent iterations. Do NOT re-derive from `current_plan` on iteration > 0: for spec/tickets the revision agent returns a bare file-path string, which would fall through to `plan` and corrupt group selection, FINALIZE routing, and review-content assembly.

   Resolution rules (applied to `current_plan` on iteration 0 only), first match wins:
   a. **Frontmatter** — after stripping a leading UTF-8 BOM and any leading whitespace/blank lines, if the text begins with a YAML frontmatter block (`---` fence) containing `artifact-type: <v>` where `<v>` is a recognized value (`spec` or `tickets`), set `artifact_type = <v>`.
   b. **Design-review sentinel** — else if the text contains `Design Decisions Reached During Grilling`, set `artifact_type = design-review`.
   c. **Plain plan** — else set `artifact_type = plan`.

   `is_design_review` is the derived predicate `artifact_type == design-review` — preserves any existing code path that branches on it. Print the resolved type on every iteration: `  artifact_type: <artifact_type>`.

2. **Assemble review content** based on `artifact_type`:

   - **`design-review`**: `current_plan` is a manifest of ADR file paths. Extract paths from the manifest body (lines after the `---` sentinel, or the plain markdown list). Verify each file exists (hard-abort naming any missing path). Read all ADR files into `adr_content` (one file-path header per file, then its content). Store `current_plan` as `plan_or_manifest`.

   - **`spec`**: on iteration 0 record `spec_file_path = pickup_path` (the path from the `pickup:` sentinel); the review content for this iteration is `current_plan` as already read. On iteration > 0, re-read the file at `spec_file_path` into `review_content`; if missing, unreadable, or empty, write `.scratch/.../dirty` (derive staging dir as parent of `spec_file_path`) and hard-stop. Store `current_plan` as `plan_or_manifest`.

   - **`tickets`**: on iteration 0 record `manifest_path = pickup_path`. On every iteration (0 and above), **re-read the manifest from `manifest_path`** — do not use `current_plan`, which is a bare path string on iteration > 0. Then assemble `review_content` as the re-read manifest body followed by the current on-disk body of every ticket file it lists, in dependency order. **Manifest-body parse rules** — ignore blank lines and `#`-prefixed comment lines; each remaining line must be a relative path (no leading `/`, no `..` segment, no shell metacharacters `;|&$()` `` ` ``); a violating or missing/unreadable path is a hard-error naming the offending path and the manifest. Store the re-read manifest content as `plan_or_manifest`.

   - **`plan`**: use `current_plan` as the review content directly. Store it as `plan_or_manifest`.

3. Store the raw artifact text as `plan_or_manifest` (set in step 2 per type above).

4. Resolve review groups before invoking the coordinator: `plan` → `A/B/C/D/E`; `design-review` → `A/B/C`; `spec` → `A/B/C/D` plus `F` only on iteration 0 when `CODEBASE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"` exists and is a readable directory; `tickets` → `A/B/C/D/E` plus `F` under the same iteration-0 pre-flight. Store the rendered list as `active_groups` and `group_f_preflight_succeeds`. Group F's pre-flight failure is non-fatal; omit it and continue with the remaining groups.

Invoke the Agent tool with:
- `description: "Critique [implementation plan|design decisions|spec|tickets] — parallel coordinator (iteration <iteration+1>)"` (select label from `artifact_type`: `plan` → "implementation plan", `design-review` → "design decisions", `spec` → "spec", `tickets` → "tickets")
- `model: <critic_model>` (from Step 1c)
- `prompt` (prepend the higher-effort line if `critic_effort == higher`):
  ```
  You are a parallel critic coordinator. The orchestrator has resolved the active groups; spawn exactly those groups IN A SINGLE MESSAGE so they run in parallel: `<active_groups>` (design-review: A/B/C; spec: A/B/C/D on iteration > 0, A/B/C/D/F on iteration 0 when Group F pre-flight succeeds; tickets: A/B/C/D/E on iteration > 0, A/B/C/D/E/F on iteration 0 when Group F pre-flight succeeds; plan: A/B/C/D/E). Each sub-agent reviews the full artifact through its assigned lenses only. After all sub-agents respond, merge their verdicts and return a single JSON result.

  Each sub-agent MUST return a raw JSON object (no markdown fences, no preamble) with exactly these fields:
  - "verdict": "approve" or "revise"
  - "severity": "none" (no issues), "minor" (small improvements only), or "major" (significant problems)
  - "top_issues": array of concise strings (empty array if none)
  - "suggested_fixes": array of concise strings (empty array if none)

  Prefix each top issue with your group and its own severity: `[<group>][major|minor] <claim> — <evidence>`. Preserve these prefixes in the merged output so the orchestrator can persist the issue ledger and send only major findings to the revision agent.

  APPROVAL RULE for each sub-agent: set "verdict" to "approve" when no major issues remain in its assigned lenses. "severity": "none" if ready as-is; "minor" if optional improvements only; "major" if significant problems. Do NOT invent concerns — only flag real, task-relevant gaps.

  Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`.

  [IF iteration >= 2 AND critic_induced_constructs is non-empty]
  CRITIC-INDUCED CONSTRUCTS (findings about these are capped at `minor` severity after pass 2):
  [insert each ledger construct as "- <name> (introduced pass <introduced_pass>)"]
  [END IF]

  ---

  SUB-AGENT PROMPTS (spawn all in a single message):

  GROUP A — Completeness & Scope:
  You are an adversarial reviewer focused on COMPLETENESS and SCOPE. Evaluate ONLY:
  - Scope creep / under-scoping: does the [plan|design] do more than needed or miss steps clearly required for the task?
  - Simplicity: is there a simpler approach with fewer moving parts or fewer assumptions?
  Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`.
  Return ONLY raw JSON: { "verdict", "severity", "top_issues", "suggested_fixes" }
  [ARTIFACT]

  GROUP B — Consistency & Coherence:
  You are an adversarial reviewer focused on CONSISTENCY and COHERENCE. Evaluate ONLY:
  - Hidden assumptions: what does this assume about the environment, existing code, dependencies, or user behavior that is not explicitly stated or verified?
  - Consistency and contradictions: does the [plan|design] contradict itself or make incompatible choices?
  - Trade-off justification: are decisions justified with stated reasons and considered alternatives?
  Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`.
  Return ONLY raw JSON: { "verdict", "severity", "top_issues", "suggested_fixes" }
  [ARTIFACT]

  GROUP C — Edge Cases & Robustness:
  You are an adversarial reviewer focused on EDGE CASES and ROBUSTNESS. Evaluate ONLY:
  - Missing edge cases: what inputs, states, conditions, or scenarios are not handled? Think: empty inputs, concurrent access, permission errors, network failures, boundary conditions.
  [IF artifact_type == plan]
  - Failure modes and rollback: what happens when each step fails? Is there a rollback path? Are there irreversible operations with no guard?
  [END IF]
  Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`.
  Return ONLY raw JSON: { "verdict", "severity", "top_issues", "suggested_fixes" }
  [ARTIFACT]

  [IF artifact_type == plan]
  GROUP D — Execution & Ordering:
  You are an adversarial reviewer focused on EXECUTION ORDER and VERIFICATION. Evaluate ONLY:
  - Ordering and sequencing: are there steps that must happen before others but are not ordered that way? Could parallelism cause race conditions or conflicts?
  - Testability and verification: how will the implementer know each step succeeded? Are there missing verification steps or acceptance criteria?
  Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`.
  Return ONLY raw JSON: { "verdict", "severity", "top_issues", "suggested_fixes" }
  [ARTIFACT]

  GROUP E — Operational Concerns:
  You are an adversarial reviewer focused on OPERATIONAL CONCERNS. Evaluate ONLY:
  - Operational concerns: where relevant, are logging, monitoring, configuration, migration, and rollout addressed? If this plan has no operational surface, approve immediately with severity "none".
  Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`.
  Return ONLY raw JSON: { "verdict", "severity", "top_issues", "suggested_fixes" }
  [ARTIFACT]
  [END IF]

  [IF artifact_type == spec]
  GROUP D — Requirement Traceability:
  You are an adversarial reviewer focused on REQUIREMENT TRACEABILITY (internal-consistency only). Evaluate ONLY:
  - Are requirement IDs (e.g. `REQ-XXXX`) used consistently *within the spec itself*? Every user story or implementation decision that cites an ID must resolve against the spec's own `Requirements:` mapping; the mapping must not cite IDs that no story covers, and no story may cite an ID absent from the mapping.
  - **Out of scope:** verifying that a REQ-ID exists in the external requirements corpus — only the draft spec file is passed to critic, so external corpus membership cannot be checked here.
  Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`.
  Return ONLY raw JSON: { "verdict", "severity", "top_issues", "suggested_fixes" }
  [ARTIFACT]
  [END IF]

  [IF artifact_type == tickets]
  GROUP D — Slice Boundaries:
  You are an adversarial reviewer focused on SLICE BOUNDARIES. Evaluate ONLY:
  - Does each slice cut a complete vertical path (schema→API→UI→tests)?
  - Is each slice demoable and sized to fit in one fresh context window?
  - Is the blocking-edge topology acyclic, free of dangling `Blocked by` references, and correctly ordered (prefactors before dependents)?
  Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`.
  Return ONLY raw JSON: { "verdict", "severity", "top_issues", "suggested_fixes" }
  [ARTIFACT]

  GROUP E — Cross-Artifact Contract Consistency:
  You are an adversarial reviewer focused on CROSS-ARTIFACT CONTRACT CONSISTENCY. Evaluate ONLY:
  - Config-key names across ticket definitions and reads.
  - Type-identifier consistency (for example, `setup_id` as int, str, or UUID) across all references.
  - Audit-string vocabulary for tickets sharing a domain entity.
  - Duplicate ownership of entity creation, migration, or deletion.
  - Every `Blocked by` reference resolving to a slug present in the manifest.
  Each major finding must cite the ticket slug(s) and exact field/value discrepancy.
  Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`.
  Return ONLY raw JSON: { "verdict", "severity", "top_issues", "suggested_fixes" }
  [ARTIFACT]
  [END IF]

  [IF artifact_type IN {spec, tickets} AND iteration == 0 AND group_f_preflight_succeeds]
  GROUP F — Codebase Grounding:
  You are an adversarial reviewer focused on CODEBASE GROUNDING. `CODEBASE_ROOT` is provided below. Evaluate ONLY:
  - Verify every named existing function, method, class, config key, schema field, DB column, and type cited by the artifact exists at its cited location.
  - Do not flag intentionally new artifacts.
  - For an absent artifact, cite the search performed and the artifact quote that names it. A `file:line` citation is mandatory for findings about present code; absence findings instead require the failed search evidence.
  Search source code conceptually and cross-file, search docs and requirements as a document corpus, and for architecture-level questions start with a global search before reading individual files. Use `rg`, `fd`, and Read for exact or local lookups when semantic search is unavailable.
  Every `major`-severity issue must cite evidence: an artifact quote, a `file:line` citation (for codebase findings), or a scenario articulation explaining which specific part of the artifact is affected. Speculative concerns without evidence are capped at `minor`.
  Return ONLY raw JSON: { "verdict", "severity", "top_issues", "suggested_fixes" }
  [ARTIFACT]
  [END IF]

  ---

  MERGE RULE (after all sub-agents respond):
  - severity: highest across all sub-agents (major > minor > none)
  - verdict: "revise" if severity == "major"; "approve" otherwise
  - top_issues: concatenate all arrays; remove obvious duplicates
  - suggested_fixes: concatenate all arrays; remove obvious duplicates

  Return ONLY the merged JSON object — no markdown fences, no preamble:
  { "verdict": "...", "severity": "...", "top_issues": [...], "suggested_fixes": [...] }

  ---

  [IF artifact_type IN {spec, tickets}]
  CODEBASE_ROOT: <CODEBASE_ROOT derived from $CLAUDE_PROJECT_DIR, falling back to $PWD; Group F is omitted when this is not a readable directory>
  [END IF]

  [IF artifact_type == design-review]
  MANIFEST:
  [insert plan_or_manifest verbatim]

  REFERENCED ADR FILES:
  [insert adr_content verbatim (concatenated ADR files with file-path headers)]
  [ELSE IF artifact_type IN {spec, tickets}]
  ARTIFACT (artifact_type: <artifact_type>):
  [insert review_content verbatim — for spec: the current on-disk spec body (re-read from spec_file_path on iteration > 0); for tickets: the manifest body followed by all ticket file bodies in dependency order]
  [ELSE]
  PLAN:
  [insert plan_or_manifest verbatim]
  [END IF]
  ```

**Parse and validate the critic response:**

Generate a unique temp-file path:
```bash
tmpfile="$(mktemp -u /tmp/pwc_critic.XXXXXX)"
```

Write the agent's returned text to `$tmpfile` using the Write tool. Then validate:
```bash
CRITIC_TMPFILE="$tmpfile" python3 - <<'PYEOF'
import json, sys, os

with open(os.environ['CRITIC_TMPFILE']) as f:
    raw = f.read().strip()

if raw.startswith('```'):
    parts = raw.split('```')
    raw = parts[1]
    if raw.startswith('json'):
        raw = raw[4:]
    raw = raw.strip()

try:
    data = json.loads(raw)
except json.JSONDecodeError as e:
    print(f"PARSE_ERROR: {e}", file=sys.stderr)
    sys.exit(1)

for field, valid in [('verdict', {'approve','revise'}), ('severity', {'none','minor','major'})]:
    if field not in data:
        print(f"MISSING_FIELD: {field}", file=sys.stderr)
        sys.exit(1)
    if data[field] not in valid:
        print(f"INVALID_VALUE: {field}={data[field]!r}", file=sys.stderr)
        sys.exit(1)

if data['verdict'] == 'approve' and data['severity'] == 'major':
    print(f"INVALID_COMBINATION: verdict=approve cannot have severity=major", file=sys.stderr)
    sys.exit(1)

if data['verdict'] == 'revise' and data['severity'] == 'none':
    print(f"INVALID_COMBINATION: verdict=revise cannot have severity=none", file=sys.stderr)
    sys.exit(1)

for field in ('top_issues', 'suggested_fixes'):
    if field not in data or not isinstance(data[field], list):
        print(f"MISSING_OR_INVALID: {field}", file=sys.stderr)
        sys.exit(1)

print(json.dumps(data))
PYEOF
```

On non-zero exit: run `rm -f "$tmpfile"`, then hard abort: "Critic agent returned invalid output at iteration `<iteration+1>`: `<stderr content>`."
On success: run `rm -f "$tmpfile"`.

Parse every issue string for its group and severity prefix before ledger persistence. The coordinator must preserve group and severity in each `top_issues` item (for example: `[A][major] claim — evidence`). Upsert the result into `critic_ledger_path` as defined in Loop state and critic ledger, set unresolved old claims to `fixed` only when absent from this REVIEW_STEP, and recompute the count of open major records. On pass 2+, compare that count to the prior pass and set `halt_convergence_guard` when it is non-decreasing.

Store: `last_verdict`, `last_severity`, `last_top_issues`, `last_suggested_fixes`, `halt_convergence_guard`.

Print: `  critic #<iteration+1>   (agent)   <verdict> (<severity>)`

Return `{ verdict: last_verdict, severity: last_severity, issues: last_top_issues, fixes: last_suggested_fixes }`.

---

### FINALIZE_STEP — Write plan and exit plan mode

**Compose enriched plan content:**

Exhaustion banner (only when cap reached without approval):
```
⚠ Reached MAX_ITERATIONS (<MAX_ITERATIONS>) without critic approval. Presenting the best available plan; unresolved issues are listed under Critic Review.

---

```

Assemble:
```
<banner (if any)><current_plan>

---

## Session Ledger

| Role         | Outcome                  |
|--------------|--------------------------|
| orchestrator | —                        |
| planner      | complete                 |
| critic #1    | <verdict> (<severity>)   |
| critic #N    | <verdict> (<severity>)   |

## Critic Review

- **Final verdict:** <last_verdict>
- **Severity:** <last_severity>
- **Iterations used:** <iteration+1> of <MAX_ITERATIONS>
- **Approval status:** <"✓ Automatically approved by critic. No manual review required." if auto_approval; "Requires manual review and approval." otherwise>
- **Remaining risks / open questions:** <last_top_issues as bullets, or "none" if verdict is "approve" and severity is "none"; optional improvements may still be listed when verdict is "approve" and severity is "minor">
```

**Detect plan-mode availability:**

Check whether `EnterPlanMode` and `ExitPlanMode` appear in the available tool list (look in the system prompt's tool list). Store as `plan_mode_available` (boolean). All plan-mode transitions below are conditional on this flag.

**Write plan/ledger file (`artifact_type IN {plan, design-review}` only):**

For `artifact_type IN {spec, tickets}`: **skip the file write entirely.** The staged artifact on disk is correct and must not be overwritten — the synthesizer maintained it in place during revisions, and `to-spec`/`to-tickets` will read and publish it as-is. Instead, print the Session Ledger and Critic Review assembled above as conversation text so the outcome is visible to the calling skill. Do not touch `plan_file_path`.

For `artifact_type IN {plan, design-review}`:

- **Plan mode available, FRESH**: call `EnterPlanMode` first, then write enriched content to the active plan file using the Write tool.
- **Plan mode available, PICKUP**: session is already in plan mode — do NOT call `EnterPlanMode`; write directly to `plan_file_path`.
- **Plan mode unavailable (agent / headless run)**: write enriched content directly to `plan_file_path`. For FRESH mode without an explicit `plan_file_path`, derive one as `~/.claude/plans/<CLAUDE_CODE_SESSION_ID>-plan.md`. After writing, present the enriched plan content as text in the conversation.

**Write verification** (`artifact_type IN {plan, design-review}` only): re-read the file and assert the original `current_plan` text is a substring of the file content. Hard abort if not: `Plan write verification failed — file does not contain the expected plan body.`

**Branch on auto_approval:**

If `auto_approval == True`:
1. If `plan_mode_available`: call `ExitPlanMode`.
2. Print: `✓ Plan automatically approved by critic. Proceeding to plan execution…` (for `artifact_type == plan`); or `✓ Artifact approved by critic.` (for `spec`, `tickets`, or `design-review`).
3. Print: `PLAN_APPROVED_READY_FOR_FINALIZATION: <plan_file_path>`
4. **Branch on `artifact_type`:**
   - **`plan`**: Read the verified plan file and proceed directly to implementation **in this same orchestrator response** — no separate user confirmation required. Decompose the approved plan into independent phases — phases with no shared-file dependencies. When ≥3 independent phases exist (advisory floor — fall back to serial if phases share heavy context), launch one Agent subagent per phase **in a single message** so they execute in parallel. Each subagent implements and tests its phase, writing only to files owned by that phase. After all report back, run a reconciliation pass: cross-module consistency (entity fields, API signatures, event contracts), then the full test suite and lint; fix any mismatches before committing. If fewer than 3 independent phases exist or any subagent fails, implement the remaining phases serially in the main conversation. Commit only when all checks pass. Only pause for a product decision, a destructive or shared-system action, or genuine ambiguity that cannot be resolved by reading specs and code.
   - **`design-review`**: the ADRs are the artifact. No implementation step — return control to the caller.
   - **`spec` or `tickets`**: do **not** implement. The sentinel printed in step 3 is the signal; the calling skill (`to-spec` or `to-tickets`) handles publishing. Return control to the calling skill.

If `auto_approval == False`:
1. If `plan_mode_available`: call `ExitPlanMode` to present the plan for manual review.
2. Return.

`auto_approval` is the only gate for automatic execution. It is `True` only when verdict is `approve`, severity is not `major`, and the iteration cap/backstop was not reached. Any other outcome (revise, major severity, cap exhaustion, invalid agent output, plan-write verification failure, or hard-abort) leaves `auto_approval` False and stops without execution.

---

## Hard invariants

- Do NOT launch headless `claude` CLI processes via Bash.
- Never pass task or plan text as shell arguments. Write to temp files for Bash.
- Bash non-zero exit, unparseable critic JSON, or missing/invalid required field = hard abort. Never treat as approval or revise.
- Do NOT call ExitPlanMode if the plan has not received a successful critic review (verdict="approve"), EXCEPT when the iteration cap is reached. When `plan_mode_available` is false, skip all ExitPlanMode calls.
- `rm -f "$tmpfile"` must run on every exit path, including hard-abort paths.

