---
name: ask-peer-model
description: Consult a second LLM through the cline-bridge MCP tools. Use when you want a design or argument stress-tested by a model that has not seen your context, when delegating work that runs for minutes, when holding a multi-turn conversation with the peer model, when deciding whether a question is worth the turn, or when a call comes back failed and you need to know what to do next.
---

# Ask a peer model

Three tools reach a different LLM, running as a Cline worker on this machine and unreachable by any API key from this side. Each costs a full turn on the far side.

- `ask_peer_model(question, repo_path)` — blocks up to 180 seconds. Use it when you want the answer in this turn.
- `submit_to_peer_model(question, repo_path, thread_id=None)` — returns a handle at once. Use it for work measured in minutes, and to hold a conversation.
- `poll_peer_model(handle, thread_id=None)` — never blocks; reads the state of a submitted question.

Operator setup — starting the worker, the watchdog, the queue — lives in `mcp/cline-bridge/README.md`.

## What the far model can and can't reach

`repo_path` is required on every call: it is the live working tree you are in right now, uncommitted work and all, and the worker reads **and edits** it. Its edits land in your tree and show up in `git diff` — there is no clone and no staging, so treat a delegated edit as a change you now own and review. It writes nothing outside `repo_path`, nor under `.git/`, `.env*`, or build directories, but that is a convention the worker keeps, not a wall: Cline enforces no path containment at all. Reads inside `repo_path` are unconstrained, so do not delegate a tree holding production credentials.

It also has bash, which reaches the whole filesystem the OS user can read — not just `repo_path`. If the artifact is a file, **pass an absolute path** rather than pasting its contents; the worker can read it itself.

What it doesn't have: no skills, no MCP tools, no credentialed services (mail, browser auth, this repo's own tooling), and no conversation history or memory of this project beyond what the question states.

It also will not reliably choose to verify before answering, and will not tell you when it is guessing. Name a repo-local artifact without pointing it at a path and it answers confidently from general knowledge, inventing specifics that read exactly like real ones. Measured across this bridge's first five round-trips:

- *"Explain the claim primitive in ADR-0069"* returned a fluent essay on Redis set-if-not-exists and database compare-and-swap. ADR-0069 uses neither.
- *"The difference between RETENTION_SECONDS and STALE_HEARTBEAT_SECONDS"* returned invented values and a lease-expiry recovery model — the exact design this bridge considered and rejected.
- The one fully accurate answer quoted text that had been pasted into the worker's own prompt.

So **give the worker a way to ground every fact the answer depends on**: an absolute path it can read for anything already on disk, or the pasted code/numbers/constraint/decision itself for anything that isn't. Reserve full inlining for what the worker cannot reach by reading — a decision not yet written down, prose that only exists in this conversation, ephemeral state. A question that names something without either a path or a quote produces fiction that sounds like knowledge.

## Worth a turn?

Ask when an independent read is the whole point:

- A design or plan you want stress-tested by something your reasoning has not anchored
- A judgement call where your own context may be biasing you
- Prose or an argument you want reacted to cold

Answer it yourself when you hold the repo and it does not: anything about this codebase's actual state, any lookup, anything greppable in less than 180 seconds.

## Writing the question

Self-contained, and long is fine — the cost is the turn, not the tokens. Include what you would hand a sharp contractor who walked in this second: the relevant code or text in full, the decision you are trying to make, and what you have already ruled out.

Say what you want back — a verdict, a critique, options with tradeoffs.

## Delegating, and holding a thread

Submit instead of asking when the work is bigger than one question — a refactor to carry out, a file to write, anything you would rather not hold a turn open for. `submit_to_peer_model` returns `{handle, status, reason}` immediately; keep the handle and collect the answer with `poll_peer_model` when you next have a reason to check. Submit several before polling any of them if the work is parallel. A request nobody answers within 30 minutes expires and polls back as failed.

Pass a `thread_id` — any string you pick — to keep a follow-up in the **same worker session**, so it still holds the earlier turns and you do not re-send them. Four rules govern a thread:

- **The first message binds `repo_path`.** Every later message must pass the same one, or submit fails with `repo_path_mismatch`.
- **Send serially.** Wait for one message to come back answered before submitting the next. Two in flight at once are not both reachable, because the thread only becomes a thread once a worker claims into it.
- **Poll with the same `thread_id` you submitted with.** Without it the handle reads back as `unknown_handle`.
- **Follow up within five minutes of each answer.** That is the worker's idle window; past it the worker leaves and the thread closes.

Missing the window is not an error and gives you no signal: a later message in a closed thread is still accepted and still answered, but by a fresh worker with none of the conversation. So if the continuity is the point, either have the follow-up ready when the answer lands, or make each message self-contained and treat the thread as a bonus.

## Reading the result

`ask_peer_model` returns `{id, status, answer, reason}`; `poll_peer_model` returns the same without `id`, and adds `status: "pending"` — still queued or being worked on, so check back rather than resubmitting.

- **`status: "answered"`** — one opinion from a model that saw only your question. Check it against the repo before you act on it; it holds no authority over what is actually in the code.
- **`reason: "worker_offline"`** — nobody is running the worker, caught before enqueuing so it returns instantly. This result carries a `watchdog` field saying whether the failure fixes itself. `watchdog: "alive"` means a restart is already due within about five minutes, so wait and retry once. `watchdog: "offline"` means the watchdog is dead too and nothing will bring the worker back — tell the human to start both, and do not retry until they say they have.
- **`reason: "timeout"`** — the worker took the question and died holding it. Claims are permanent, so that question is terminal and no later worker will ever see it; the record stays under `failed/` for the post-mortem. Resubmit only once you know a fresh worker is up.
- **`reason: "queue_unavailable"`** — the queue directory is unwritable. A filesystem problem for the human to fix.
- **`reason: "unknown_handle"`** (poll only) — no such request. Either the `thread_id` does not match the one you submitted with, or the handle is past the 7-day history. Check the `thread_id` before concluding the request is gone.
- **`reason: "repo_path_mismatch"`** (submit only) — this thread's first message bound a different `repo_path`. Resend with that one, or start a new thread.

Treat any reason you do not recognise as terminal, not as pending.
