# GENERATE_STEP planner/reviser prompts

These are the two agent-prompt templates GENERATE_STEP assembles and sends to the Agent tool (`subagent_type: "claude"`). Honour the `[IF …]`/`[insert … verbatim]`/`[ELSE …]` directives against the resolved `artifact_type`, `MODE`, and `user_answers`. The orchestrator's post-processing (annotation extraction, path validation, FLAGGED_DECISIONS parsing) lives in SKILL.md, not here.

## Initial plan (`iteration == 0`, FRESH)

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

## Revision (`iteration > 0`)

- `description: "Revise [implementation plan|design decisions] based on critic feedback"`
- `prompt`:
  ```
  [IF dr]
  You are a design decision critic's assistant. Revise the ADR files to address the critic's feedback on your design decisions.

  **IMPORTANT**: You have Write and Edit tool access. For each ADR file listed in the manifest, read it, apply the fixes suggested by the critic, and **edit the file in place** using the Edit tool. Do NOT attempt to return revised file content in text — the files are your artifact.
  You may use the Agent tool to spawn sub-agents for major parallel revision tasks if useful, but MUST return a single coherent manifest text as your final output.

  After editing the ADR files, return ONLY the manifest text — no preamble, no closing remarks. The manifest should still list all the same ADR file paths (unchanged), because the actual revisions are in the files you just edited.
  [ELSE IF artifact_type == spec]
  You are a spec writer's assistant. Revise the staged spec file to address the critic's feedback.

  **IMPORTANT**: You have Write and Edit tool access. Read the spec at `<spec_path>`. Retain the `artifact-type: spec` frontmatter block at the top of the file — it must not be removed. Apply the critic's fixes by editing the file in place using the Edit tool. Do NOT return revised spec text in your response.

  Return the spec file path as the first line. Then emit zero or more `INTRODUCED: [name]` or `ACCEPTED: [ID] [reason]` lines; no other output.
  [ELSE IF artifact_type == tickets]
  You are a ticket author's assistant. Revise the staged ticket files and manifest to address the critic's feedback.

  **IMPORTANT**: You have Write and Edit tool access. Read the manifest at `<manifest_path>` and all ticket files it references. Edit them in place. You may change content within a ticket file (edit that file), add a slice (write a new ticket file and append its path to the manifest in dependency order), or remove/renumber a slice (delete/rename the ticket file, update the manifest, and update every sibling `Blocked by` reference that pointed at the changed slug so no dangling edges remain).

  After all edits, run post-edit validation and assert: (a) every manifest path refers to an existing, readable file; (b) every `Blocked by` reference in every ticket resolves to a slug present in the manifest; (c) no staged ticket file is absent from the manifest; (d) the `Blocked by` graph is acyclic and no ticket blocks itself. If any assertion fails, write a `dirty` marker file at `.scratch/.../dirty` (derive staging dir as the parent directory of the manifest), report the specific inconsistency, and stop rather than returning.

  Return the manifest file path as the first line. Then emit zero or more `INTRODUCED: [name]` or `ACCEPTED: [ID] [reason]` lines; no other output.
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

  [IF dr]
  MANIFEST (ADR file paths):
  [insert artifact verbatim]

  CURRENT ADR FILES (content):
  [insert adr_content verbatim]
  [ELSE IF artifact_type == spec]
  STAGED SPEC PATH:
  [insert spec_path verbatim]

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
  [insert each `top_issues` item whose `[severity]` prefix is `[major]` as "- <item>"]

  SUGGESTED FIXES:
  [insert suggested fixes that correspond to the listed major issues only]

  If you introduce new functions, classes, configuration keys, or machinery, append one line per construct: `INTRODUCED: [name]`. If a major should remain unchanged because the artifact deliberately accepts its risk, append `ACCEPTED: [ID] [reason]`; acceptance requires user confirmation in guided mode and is unavailable in auto mode. For `spec` and `tickets`, emit annotations only after the required path on the first line. For plan and design-review, append them after the artifact or manifest.
  Note: the [design|plan] will not be approved until all major issues are resolved. Minor improvements may still be noted on approval.
  ```
