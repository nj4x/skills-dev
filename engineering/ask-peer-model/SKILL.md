---
name: ask-peer-model
description: Consult a second LLM through the cline-bridge MCP tool. Use when you want a design or argument stress-tested by a model that has not seen your context, when deciding whether a question is worth the turn, or when `ask_peer_model` comes back failed and you need to know what to do next.
---

# Ask a peer model

`ask_peer_model(question)` reaches a different LLM, running as a Cline worker on this machine and unreachable by any API key from this side. It blocks for up to 180 seconds and costs a full turn on the far side.

Operator setup — starting the worker, the watchdog, the queue — lives in `mcp/cline-bridge/README.md`.

## The far model is blind

It has bash and nothing else: no repository, no files, no conversation history, no knowledge that this project exists. It cannot look anything up.

It also will not tell you when it is guessing. Name a repo-local artifact and it answers confidently from general knowledge, inventing specifics that read exactly like real ones. Measured across this bridge's first five round-trips:

- *"Explain the claim primitive in ADR-0069"* returned a fluent essay on Redis set-if-not-exists and database compare-and-swap. ADR-0069 uses neither.
- *"The difference between RETENTION_SECONDS and STALE_HEARTBEAT_SECONDS"* returned invented values and a lease-expiry recovery model — the exact design this bridge considered and rejected.
- The one fully accurate answer quoted text that had been pasted into the worker's own prompt.

So **inline every fact the answer depends on**. Paste the code, the numbers, the constraint, the decision itself. A question that names something instead of quoting it produces fiction that sounds like knowledge.

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
- **`reason: "worker_offline"`** — nobody is running the worker, caught before enqueuing so it returns instantly. Tell the human to start it; one call is enough to learn this.
- **`reason: "timeout"`** — the worker took the question and died holding it. Claims are permanent, so that question is terminal and no later worker will ever see it; the record stays under `failed/` for the post-mortem. Resubmit only once you know a fresh worker is up.
- **`reason: "queue_unavailable"`** — the queue directory is unwritable. A filesystem problem for the human to fix.
