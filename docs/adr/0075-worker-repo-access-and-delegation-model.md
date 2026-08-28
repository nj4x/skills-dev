---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0075: Worker Repo Access and Delegation Model

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.

**Status**: Approved

**Known Risks (Accepted)**

1. **Worker writes are uncontained at the filesystem level.** Cline has zero path containment on `write_to_file`, `replace_in_file`, and `execute_command` — the fork's `validateDestructiveCommand` is dead code (documented in ADR-0053 §Detailed Findings). A worker can write anywhere the hosting user can write, including outside `repo_path`, and can escalate via `sudo` if passwordless sudo is configured. **Mitigation**: the delegation model is opt-in — the capable agent that opens a worker window is responsible for trusting that window. The prompt rule against exfiltration is guidance, not a boundary. Post-answer review (ticket #57's async surface + manual inspection before accepting the answer) is available if the question involves sensitive edits.

2. **Tree mutations during answer are unguarded.** The capable agent may edit the repo while the worker reads it, yielding a torn read. **Mitigation**: the worker's rendered claim includes the files it reads; the answer records which files were touched, allowing the capable agent to spot staleness. This is prompt-level (one sentence) and does not require schema changes.

3. **No rollback or diff of worker writes.** If a worker edits `src/main.rs` and the capable agent disagrees with the edit, there is no automatic diff — the agent must inspect the working tree. **Mitigation**: the editing surface is narrowed (see Consequences, Write Scope below), and edits are legible in `git diff` because the repo is a working tree, not a clone.

**Context**

Map issue #52 extends cline-bridge with threaded conversations and a worker pool, fixing v1's confabulation (worker cannot see the repo). ADR-0053 audited trust boundaries for read-only access; ticket #54 locked thread and worker-pool architecture; ADR-0073 and ADR-0074 settled queue schema and worker registration. Ticket #58 settles the provisioning strategy for worker repo access.

The key tension: #53's recommendation (shallow clone with OS-level immutability) provides isolation but at the cost of the worker being blind *again* to uncommitted work, unpushed branches, and the true state of the codebase. The capable agent working in that repo right now would have to extract and send diffs manually — defeating the confabulation fix and the whole point of delegation.

The user's direction reframes the problem: the worker is not an untrusted sandbox. It is a **delegate** — a model running in the capable agent's own VS Code window, in the capable agent's user session, answering questions on behalf of that agent. The threat model is not "contain a malicious model" but "enable a helpful model to edit code without breaking the repo, and let the capable agent decide what to trust."

**Decision**

## Worker accesses the live working tree, with no clone or staging

The worker reads and edits the actual `repo_path` that the capable agent is working in, at the moment the agent delegates. This is the only way to fix confabulation without losing visibility to uncommitted work, uncommitted branches, and the live state of the tree.

`ask_peer_model` takes a new required parameter `repo_path` (string, validated as an existing directory at submit):

```python
ask_peer_model(question: str, repo_path: str) -> dict
```

The capable agent supplies this at every call. `repo_path` is stored on the record and passed to the worker on claim. The worker's rendered claim includes `repo_path` as the working directory.

There is no clone, no shallow copy, no staging directory, and no immutability enforcement (`chmod -R a-w`).

## Reads are unconstrained within `repo_path`; writes have a default denylist

**Read access:** the worker can read any file within `repo_path`, including `.env`, git history, and private branches — limited only by the filesystem permissions of the hosting user. This is the cost of fixing confabulation.

**Write access:** the worker can edit files within `repo_path`, but not outside it. The default denylist blocks writes to:

- `.git/`
- `.env*` (any file matching the pattern)
- `node_modules/`, `.venv/`, `target/`, `build/`, and other common build/vendor directories
- Editor config (`.vscode/`, `.idea/`, `.DS_Store`, etc.)

The denylist is enforced as a prompt rule and validated post-submission: `bridge answer` rejects any file listed in the denylist. This is a soft enforcement — a tool-side check that stops obvious mistakes, not a security boundary.

## Per-record `repo_path` with thread-level validation

Every record stores `repo_path`. For threaded records, the first message in the thread sets the path; subsequent messages in that thread must specify the same path or fail at submit. This prevents mid-thread repo switches that would invalidate the worker's session context.

Server-side validation:

```python
if record["thread_id"] is not None:
    first = queue.read_first_in_thread(record["thread_id"])
    if first["repo_path"] != repo_path:
        raise ValueError(f"repo_path mismatch: thread uses {first['repo_path']}, got {repo_path}")
```

## Delegation model: the worker is trusted because the capable agent opened the window

A worker is not a sandbox. The capable agent that opens a Cline task in VS Code is responsible for trusting the model that runs in it. The model is Claude, and the session runs in the user's own environment with the user's own credentials, permissions, and files.

The implications:

- **The worker can edit code.** It is a delegate, not a read-only oracle.
- **The worker can read secrets and private code.** There is no in-app isolation. The capable agent should not open a worker pool if the repo contains production credentials, and should manually review answers if the question involves sensitive edits.
- **Opening a worker pool is a conscious choice.** It is not automatic or default. The capable agent opts in by calling `ask_peer_model` with `repo_path`. If the repo is sensitive, don't do that.

Document this in the worker prompt and `.clinerules/` as guidance, not a boundary condition.

## Answer-side fencing is guidance, not a requirement

ADR-0053 recommended that answers be scanned or reviewed to prevent exfiltration. This decision reframes it: because the worker reads the live tree, exfiltration is a parameter of the delegation, not a surprise. If the capable agent trusts the worker to edit `src/main.rs`, it should also expect the worker can read and report on `.env` if asked.

Post-answer review is available via the async surface (#57) — the capable agent can inspect the staged answer before accepting it — but the mechanism is optional. The prompt includes a rule: "Never include secrets, credentials, or proprietary code in your answer unless the question explicitly asks for them and you are confident the capable agent intends to see them." This is guidance and relies on the model, not enforcement.

**Consequences**

- **`ask_peer_model` tool signature changes.** The new required parameter `repo_path` (string) is mandatory. Calls without it will raise `ValueError`. Backward compat: existing calls will fail fast with a clear error, surfacing the intent to add this parameter.

- **Worker prompt and `.clinerules/bridge-trust-boundary.md` must be updated.** Change "You have bash only. No repo access" to "You can read and edit the repo at `<repo_path>`. You cannot write outside it or to `.git/`, `.env*`, or build directories." Change "no way to look anything up" to clarify bash and file tools work, and now repo read is included. Keep the rule: "Never include secrets or private code in your answer unless explicitly asked." This is now a prompt convention, not a boundary enforcer.

- **`bridge/cli.py` gains `--repo-path` on `answer` subcommand.** The `_render()` function already includes it in the rendered claim; `bridge answer <id> --file <path> --repo-path <path>` validates the path on write. Invalid paths or files in the denylist are rejected with a clear error; the worker must re-edit and re-stage.

- **Queue schema adds `repo_path` field to every record.** Thread-level validation (first message sets the path) is enforced at submission time in `server.py`.

- **ADR-0053 is refuted but not deleted.** The trust audit remains load-bearing — it is why we know a clone would buy nothing. Add a header note: "This approach is superseded by ADR-0075, which accepts Cline's zero containment and reframes repo access as delegation." Delete the "Recommendation" section from ADR-0053. Update map #52's Notes and Out of Scope to reflect that v2 does not provision a separate checkout or enforce immutability.

- **Ticket #60 (worker-capability messaging) remains independent and unblocked.** It fixes the docstring and prompt today; #58's implementation will update them again. This is OK — fixing a live falsehood now is worth the overlap.

- **Tree staleness is managed by the capable agent.** If the capable agent edits the repo during the worker's answer, the worker's edits or observations are based on an older state. The protocol does not guard this — it is the price of accessing a live tree. The capable agent should be aware of this when delegating mid-edits.

---

## Record schema

```json
{
  "id": "...",
  "thread_id": "... or null",
  "question": "...",
  "repo_path": "/Users/agent/workspace/project",
  "submitted_at": "...",
  "claimed_at": null,
  "claimed_by": null,
  "answered_at": null,
  "continuation_deadline": null,
  "answer": null
}
```

**`repo_path`** (string): absolute path to the repo the worker should read and edit. Validated as an existing directory at submit; immutable once set. For threaded records, subsequent messages must use the same path.
