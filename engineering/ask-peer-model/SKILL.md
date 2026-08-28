---
name: ask-peer-model
description: Consult a second LLM through the cline-bridge MCP tool. Use when you want a design or argument stress-tested by a model that has not seen your context, when deciding whether a question is worth the turn, or when `ask_peer_model` comes back failed and you need to know what to do next.
---

# Ask a peer model

`ask_peer_model(question, repo_path)` reaches a different LLM, running as a Cline worker on this machine and unreachable by any API key from this side. It blocks for up to 180 seconds and costs a full turn on the far side.

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

## Reading the result

`{id, status, answer, reason}`.

- **`status: "answered"`** — one opinion from a model that saw only your question. Check it against the repo before you act on it; it holds no authority over what is actually in the code.
- **`reason: "worker_offline"`** — nobody is running the worker, caught before enqueuing so it returns instantly. This result carries a `watchdog` field saying whether the failure fixes itself. `watchdog: "alive"` means a restart is already due within about five minutes, so wait and retry once. `watchdog: "offline"` means the watchdog is dead too and nothing will bring the worker back — tell the human to start both, and do not retry until they say they have.
- **`reason: "timeout"`** — the worker took the question and died holding it. Claims are permanent, so that question is terminal and no later worker will ever see it; the record stays under `failed/` for the post-mortem. Resubmit only once you know a fresh worker is up.
- **`reason: "queue_unavailable"`** — the queue directory is unwritable. A filesystem problem for the human to fix.
