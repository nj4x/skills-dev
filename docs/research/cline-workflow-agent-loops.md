# Cline workflows and self-driving agent loops

Research for the "filesystem queue bridge" design: Claude Code posts questions to a shared
directory, a Cline workflow makes Cline's own backing model claim / answer / post / repeat,
with no human on the Cline side.

Date: 2026-08-26. Upstream `cline/cline` inspected at `b4fd4ee` (2026-08-27, v4.1.16 era) plus
tag `v3.26.6` as a stand-in for the "classic" VS Code extension architecture.

Reading conventions used below:

- **Documented** — stated in `docs.cline.bot` or an official blog post.
- **Source** — read out of `cline/cline`. A behaviour, not a promise; upstream can change it.
- **Inference** — my reading, flagged as such.

---

## 1. The central unknown, answered

**Yes, and the risk is the opposite of what you expect.** A Cline task does not end when the
model "feels done". Cline's agent loop is a `while` loop that keeps calling the model until
one of a small number of *blocking asks* fires. If the model replies with text and no tool
call, Cline does not stop — it injects an error telling the model to use a tool and calls the
model again.

From `src/core/task/index.ts` at `v3.26.6` (`initiateTaskLoop`, line 1192):

```ts
private async initiateTaskLoop(userContent: UserContent): Promise<void> {
	let nextUserContent = userContent
	let includeFileDetails = true
	while (!this.taskState.abort) {
		const didEndLoop = await this.recursivelyMakeClineRequests(nextUserContent, includeFileDetails)
		...
		if (didEndLoop) {
			break
		} else {
			nextUserContent = [{ type: "text", text: formatResponse.noToolsUsed() }]
			this.taskState.consecutiveMistakeCount++
		}
	}
}
```

and the injected text (`src/core/prompts/responses.ts`, still present on `main`):

```
[ERROR] You did not use a tool in your previous response! Please retry with a tool use.
...
If you have completed the user's task, use the attempt_completion tool.
If you require additional information from the user, use the ask_followup_question tool.
Otherwise, if you have not completed the task and do not need additional information, then proceed with the next step of the task.
(This is an automated message, so do not respond to it conversationally.)
```

Source: <https://github.com/cline/cline/blob/main/apps/vscode/src/core/prompts/responses.ts>

So "the agent ends its turn because the task looks done" is not a failure mode here. Cline has
no concept of a turn ending. **The loop is default-on; you have to work to stop it.**

### What actually stops the loop

Everything that halts a Cline task halts it by calling `this.ask(...)`, which blocks on a
human clicking a button in the webview. With no human on the Cline side, every one of these is
a permanent park, not a graceful stop. From `ToolExecutor.ts` and `Task.index.ts` at `v3.26.6`:

| Stopper | Mechanism | Auto-approvable? |
|---|---|---|
| `attempt_completion` | `await this.ask("completion_result", "", false)` | **No.** Not in the `shouldAutoApproveTool` switch at all. |
| `ask_followup_question` | blocking `ask` | **No.** |
| `new_task` | `await this.ask("new_task", context, false)` | **No.** |
| `condense` (model-invoked) | `await this.ask("condense", context, false)` | **No.** |
| Max auto-approved requests | `ask("auto_approval_max_req_reached", ...)` | N/A — it *is* the gate. Default 20. |
| 3 consecutive "mistakes" | `ask("mistake_limit_reached", ...)` | N/A. |
| API request failure (first chunk) | `ask("api_req_failed", ...)` after one automatic retry | N/A. |

The auto-approve allowlist is narrow and explicit — `read_file`, `list_files`,
`list_code_definition_names`, `search_files`, `new_rule`, `write_to_file`, `replace_in_file`,
`execute_command`, `browser_action`, `web_fetch`, `access_mcp_resource`, `use_mcp_tool`. Nothing
else. Source: `src/core/task/tools/autoApprove.ts` at `v3.26.6`.

### Consequences for your design

1. **Never let the model call `attempt_completion`.** That is the single dominant failure mode.
   One call parks the task forever with a "task complete" card and no one to dismiss it. The
   workflow's most important sentence is a prohibition, not an instruction to loop.
   Cline's own system prompt actively pushes the model toward `attempt_completion`, and the
   `noToolsUsed` error text names it first. You are fighting the harness on this one point.
2. **Never let it call `ask_followup_question`.** Same park. The workflow must tell the model
   what to do when the queue is empty or a question is malformed, so it never reaches for a
   human.
3. **Raise or remove the max-requests cap** (see §3). At the default of 20 you get roughly six
   to ten question-answer rounds before a hard park.
4. **The loop instruction stays in context.** The workflow body is spliced into the user
   message and lives in the conversation history for the whole task, so the model re-reads it
   on every API call — it does not decay the way a one-off instruction would. This is the
   mechanism that makes an in-conversation loop viable at all.
5. **Budget for context growth, not for the model quitting.** A long-lived loop dies from
   context exhaustion or a provider error, not from loss of will.

### Confidence

High on the loop mechanics — read directly from source and the code is unambiguous. Medium on
how it maps to *your* build: a proprietary fork can change the auto-approve allowlist, the
system prompt, and the max-requests default. §7 lists what to measure.

---

## 2. Workflows and `.clinerules`

### Where files live

| Scope | Rules | Workflows |
|---|---|---|
| Workspace | `.clinerules/` (project root) | `.clinerules/workflows/` |
| Global | `~/Documents/Cline/Rules` | `~/Documents/Cline/Workflows` |

Source: `src/core/context/instructions/user-instructions/rule-helpers.ts` (`workflows:
".clinerules/workflows"`) and `src/core/storage/disk.ts`. Documented at
<https://docs.cline.bot/customization/cline-rules>, which covers rules but — as of this
writing — no longer documents the workflows subdirectory. The current docs site has no
`/features/slash-commands/workflows` page; it 404s. Nearest live pages:
<https://docs.cline.bot/core-workflows/using-commands>.

Cline also reads `AGENTS.md` and `~/.agents/AGENTS.md`, and auto-detects `.cursorrules` /
`.windsurfrules`. Rules support optional YAML frontmatter with a `paths` key for conditional
activation; no frontmatter means always active. Documented.

### How a workflow is invoked and what the model sees

Type `/<filename>` in the chat input. The workflow file's body is read and **spliced into the
user message before it is sent**. In the classic build the body is wrapped:

```ts
const processedText =
	`<explicit_instructions type="${matchingWorkflow.fileName}">\n${workflowContent}\n</explicit_instructions>\n` +
	textWithoutSlashCommand
```

Source: `src/core/slash-commands/index.ts` at `v3.26.6`. Confirmed by Cline's own blog: "When
you type `/pr-review.md`, Cline wraps that workflow's content in `<explicit_instructions>` tags
and injects it into that specific message."
(<https://cline.bot/blog/stop-adding-rules-when-you-need-workflows>)

On current `main` the wrapping tag is gone — `expandSlashCommands` splices
`command.instructions` in verbatim:

```ts
return text.slice(0, start) + command.instructions + text.slice(end)
```

Source: `apps/vscode/src/sdk/slash-command-expansion.ts`. **Inference:** if you rely on the
model recognising `<explicit_instructions>` as a high-authority frame, do not — it is not
stable across versions. Put the authority in the prose.

### Iteration support

**There is none.** No loop construct, no `repeat`, no `while`, no re-invocation on completion.
The blog states it plainly: "The workflow executes once, completes its sequence, and
disappears." A workflow is a text blob, not a program.

The *only* thing that makes repetition work is that the blob is now permanent conversation
history and the agent loop keeps running. Repetition must be expressed as instructions the
model chooses to follow ("after posting an answer, immediately run the claim command again;
never call attempt_completion"), backed by the loop's refusal to let the model idle.

Rules (`.clinerules/*.md`) are appended to the system prompt on every request — stronger
placement, but they cost tokens on every message and are not invoked on demand. **Inference:**
for a dedicated Cline instance whose only job is the bridge, a *rule* is a better home for
"never call `attempt_completion`" than a workflow, because it sits in the system prompt where
it competes on more even footing with Cline's built-in tool guidance. Use the workflow for the
procedure and a rule for the prohibitions.

### Built-in slash commands

`/newtask`, `/smol` (alias `/compact`), `/newrule`, `/reportbug`, `/deep-planning`. All expand
to `<explicit_instructions type="...">` blocks from `src/core/prompts/commands.ts`.
Documented: <https://docs.cline.bot/core-workflows/using-commands>

---

## 3. Autonomous continuation and the request cap

### Auto-approve

Nine toggles: read project files, read all files, edit project files, edit all files, execute
safe commands, execute all commands, use the browser, use MCP servers, enable notifications.
Command safety is **not** allowlist-based — "The model marks each command with a
`requires_approval` flag based on the command and arguments." So a model that wants to keep
moving can mark its own commands safe. For your bridge you want **Execute all commands** on
regardless. Documented: <https://docs.cline.bot/features/auto-approve>

Note a documentation/source mismatch: the docs page still describes a "YOLO Mode" checkbox,
but the changelog says it was removed as cosmetic — "remove the Yolo Mode toggle, which was
cosmetic: nothing in the approval path read it. Setups that had Yolo Mode (or
auto-approve-all) turned on are migrated to auto-approving every action" (v4.1.8,
`CHANGELOG.md`). **Treat the docs page as stale on this point.** In an older fork, YOLO mode
may be equally cosmetic — check the approval path, not the checkbox.

### Max requests

Classic build: `maxRequests: 20` in `DEFAULT_AUTO_APPROVAL_SETTINGS`
(`src/shared/AutoApprovalSettings.ts` at `v3.26.6`). When the counter reaches it:

```ts
const { response, text, images, files } = await this.ask(
	"auto_approval_max_req_reached",
	`Cline has auto-approved ${this.autoApprovalSettings.maxRequests} API requests. Would you like to reset the count and proceed with the task?`,
)
```

The counter increments per auto-approved tool call, not per round trip, so a claim + answer +
post cycle burns 2–3. **20 buys you roughly 6–10 rounds.**

Two facts that help:

- The UI field is a free numeric text input (digits only, no visible ceiling) —
  `webview-ui/src/components/chat/auto-approve-menu/AutoApproveModal.tsx` at `v3.26.6`. Set it
  to something enormous.
- Changing it does **not** affect the currently open task. You must start a new task for the
  new value to apply. Reported and confirmed:
  <https://github.com/cline/cline/issues/4907>
- Hitting it with no human present is a hard lockout, not a degradation:
  <https://github.com/cline/cline/issues/3480>

Upstream removed the cap entirely in **v3.35.0** ("Auto-approve is now always-on with a
redesigned expanding menu"). Current `main` keeps the field only as a dead compatibility
stub: `maxRequests: 20, // Legacy field - kept for backward compatibility` with the comment
"Max requests limit feature has been removed"
(`apps/vscode/src/shared/AutoApprovalSettings.ts`). **Whether your fork has the cap depends
entirely on which side of v3.35.0 it forked from — measure it.**

### Continuation after a tool result

`recursivelyMakeClineRequests` calls itself with the tool results as the next user content.
No user turn is involved, ever. Source: `src/core/task/index.ts` line 2539.

### Mistake limit

Three consecutive text-only (no tool) responses trip `ask("mistake_limit_reached", ...)` and
park. The counter resets when a tool executes successfully. **Inference:** for your loop this
is a real hazard only if the model starts narrating instead of acting — e.g. "I've answered all
the questions, so I'll summarise what I did." Two such replies in a row and you are one away
from a park.

---

## 4. Documented limits

### Command / terminal timeouts

**Classic build (`v3.26.6`): `execute_command` has no command timeout.** `executeCommandTool`
does `await process` and waits for the shell process to finish. What is configurable is
`shellIntegrationTimeout`, default **4000 ms**, which only bounds how long Cline waits for VS
Code's shell integration to come up before falling back — not how long your command may run.
Source: `src/core/task/index.ts` `executeCommandTool`, and
`shellIntegrationTimeout: { default: 4000 }` in `state-keys.ts`.

While a command runs, streamed output is chunked (20 lines / 2 KB / 100 ms debounce) into
`ask("command_output", chunk)`, which surfaces a "Proceed while running" button. With nobody
to click it, the process still runs to completion — the ask governs how output is displayed,
not whether the command finishes. **Inference from reading the code; not a stated guarantee.**

**Current SDK build: there IS a command timeout, default 30 000 ms**, configurable per tool
config (`bash: { timeoutMs: 60000 }`). Source:
`sdk/packages/core/src/extensions/tools/executors/bash.ts` (`timeoutMs = 30000`) and
`extensions/tools/index.ts`.

Two behaviours on timeout, and they matter a lot to you:

1. **A timeout is returned to the model as a failed tool result, not a task abort.** The
   `TimeoutError` is caught and turned into `{ query, result, error, success: false }`.
   Source: `sdk/packages/core/src/extensions/tools/definitions.ts` lines ~180–245. **The loop
   survives a timeout.** This is the single most useful fact for a long-poll design.
2. **Where detaching is possible, Cline detaches instead of killing**, and hands the model a
   log path:

```
[Command is still running. Output will continue in ${detachedLog.path}]
```

Source: `sdk/packages/core/src/extensions/tools/executors/bash.ts`, the `detach()` closure.
This is upstream's own answer to "tool call shorter than the work": run detached, return a log
path, poll the file. If your fork predates the SDK it will not have this — but you can build
the same pattern by hand with `nohup … > logfile &`.

CLI-only knobs (not available in the extension): `-t, --timeout <seconds>` (default `0`, no
timeout) and `--retries <count>` ("halt after a set number of consecutive mistakes").
Documented: <https://docs.cline.bot/cli/cli-reference>

### Context growth

Two mechanisms, **both automatic, neither asks the user**:

- **Programmatic truncation** (default). When the previous request's token usage crosses
  `maxAllowedSize`, Cline deletes a `half` or `quarter` range from the middle of the
  conversation, always keeping the first user-assistant pair. Source:
  `src/core/context/context-management/ContextManager.ts`, `getNextTruncationRange`.
- **Auto-condense**, when enabled *and* the model is in `isNextGenModelFamily`. Cline appends
  `summarizeTask(...)` to the user content, the model produces a summary, and the pre-summary
  turns are masked out. Source: `src/core/task/index.ts` lines ~2160–2242.

Note the interaction with §2: truncation **always keeps the first user-assistant pair**, and
your workflow body is spliced into that first user message. **Inference: your loop instruction
survives truncation.** That is a genuinely favourable accident of the design, and worth
verifying in your build before you rely on it.

Failure mode: if the API returns a context-window-exceeded error, Cline retries automatically
**once**, then falls through to `ask("api_req_failed", ...)` and parks. If the truncated
history is 3 messages or fewer, the code comments call the conversation "bricked". Source:
`src/core/task/index.ts` lines ~1762–1810.

**Recommendation:** keep the per-round context footprint tiny. The claim command should return
one question, the post command should return a bare acknowledgement. Do not let question or
answer bodies accumulate in the transcript — write them to files and pass paths.

---

## 5. Prior art on agent work-queue loops

### The Ralph loop — the dominant pattern, and why it does not apply

`while :; do cat PROMPT.md | claude-code ; done`. Geoffrey Huntley, July 2025.
<https://ghuntley.com/ralph/>

Each iteration is a **fresh process with a fresh context window**; state lives in files and git,
not in the model's memory. This is the most widely adopted answer to "keep an agent working"
and it went broadly visible through late 2025 / early 2026
(<https://www.theregister.com/2026/01/27/ralph_wiggum_claude_loops/>).

**It does not transfer to your situation.** Ralph's loop is *outside* the agent — a shell `while`
around a CLI invocation. Your Cline build has no CLI, so there is no outer loop to write. You
are forced into an in-conversation loop, which is the harder variant: context accumulates, and
the loop's continuation depends on the model's compliance rather than on `bash`.

The compensating advantage, from §1: Cline's own agent loop already provides the "keep going"
force that Ralph gets from `while :;`. You are not building a loop from nothing — you are
preventing an existing loop from being stopped.

### Blocking-poll patterns

`MultiModelCLIEmail` (<https://github.com/abstractionlair/MultiModelCLIEmail>) uses Maildir to
bridge Claude Code / Codex / Gemini / OpenCode and documents exactly your loop shape:

```
while True:
    msg poll --role explorer-claude --wait
    # Process messages
    # Respond as needed
    # Loop (never ends response)
```

`msg poll --wait` blocks until a message arrives, with `--timeout N` optional (default: wait
forever). Note "never ends response" — the same instruction you need. Caveat: the repo's own
TODO list flags that the launcher script for the persistent-agent flow is unbuilt, so treat
this as a documented design rather than a proven one.

Related work in the same shape: "Postal" (SQLite-backed mailbox, `check_mailbox()` blocks until
a message arrives), `mcp-talk` (JSON files per message, namespace isolation),
`mcp-multiagent-bridge` (two Claude Code sessions over an MCP server), and file-based
message-bus skills. All are MCP servers, so none of them are directly usable from a build that
cannot load MCP — but the queue semantics are worth copying.

### The blocking-poll / tool-timeout collision

This is the sharp edge in your design, and the literature does not solve it. A blocking
`claim-next-question --wait` is the clean way to avoid a busy-spin, but it collides with a bash
tool timeout. Three options, in the order I would try them:

1. **Bounded blocking poll.** `claim-next --wait --timeout 20` where 20 s is comfortably under
   the tool timeout. Empty result is a normal, expected outcome and the workflow says so
   explicitly: "if it prints `NO_QUESTIONS`, run the same command again." This keeps the
   round-trip count high (each empty poll burns an auto-approve slot) but is the simplest thing
   that works.
2. **Detached poll + log tail** — upstream Cline's own pattern (§4). `nohup claim-next --wait >
   /tmp/q.log &`, then `sleep 20; cat /tmp/q.log`. Survives tool timeouts by construction and
   burns fewer requests per unit of wall-clock wait.
3. **Sleep-and-check.** `sleep 30 && claim-next`. Crude, and a `sleep` longer than the tool
   timeout will be killed — so the sleep must also stay under it.

**Inference, not measured:** option 1 is the right starting point because it fails visibly. If
polls are burning too many requests, move to option 2.

### What kills agent loops

Synthesising across the write-ups above and the Cline source:

- **No stop condition stated, so the model invents one.** "The trigger has to come bundled with
  a stop condition." An agent told only "keep going" will decide for itself when the job is
  done. State the terminal condition and make it one the model will rarely reach: "run
  forever; the only reason to stop is if the claim command prints `SHUTDOWN`."
- **Ambiguity read as completion.** An empty queue is the moment the model decides it is
  finished. Name that case in the workflow and prescribe the exact next action.
- **Context exhaustion.** Handled automatically by Cline (§4), but truncation silently drops
  mid-conversation turns — a loop that depends on remembering earlier rounds will degrade.
  Design each round to be stateless.
- **Instruction decay over many rounds.** Not a factor here, per §2 — the workflow text is
  pinned in the first user message and survives truncation. Verify this in your build.
- **A real-world note on cross-agent file messaging**: one write-up
  (<https://dev.to/aviad_rozenhek_cba37e0660/communication-protocols-for-ai-agents-that-cant-talk-to-each-other-b23>)
  reports that plain file-based messages between agents were repeatedly *misunderstood* until
  the file contained explicit, unambiguous action items. Format your queue payloads as
  instructions, not as data.

---

## 6. Headless entry points in upstream Cline

Stated for completeness — your build has none of the CLI surfaces. Presented as "what the
upstream product makes possible", per the brief.

### CLI (`apps/cli`)

`cline "prompt"`, `echo "prompt" | cline`, `--json` (newline-delimited JSON events),
`--auto-approve <boolean>` (default `true` when a prompt is passed), `-t/--timeout <seconds>`,
`--retries <count>`, `--id <session-id>` to resume, `-z/--zen` to run in the background hub, and
`CLINE_COMMAND_PERMISSIONS` for allow/deny globs.
Documented: <https://docs.cline.bot/cli/cli-reference>

### Scheduled agents

`cline schedule` with cron syntax; jobs persist across process restarts and run independently
of any terminal session. Explicitly **"only applies to Cline SDK, CLI, and Kanban"** — *not*
VS Code or JetBrains. Documented: <https://docs.cline.bot/cli/scheduling>

### The `vscode://` task URI — the interesting one

Current `main` registers a URI handler with a `/task` route:

```ts
case TASK_URI_PATH: {          // "/task"
	const prompt = query.get("prompt")
	if (prompt) {
		await visibleWebview.controller.handleTaskCreation(prompt)
		return true
	}
}
```

Source: `apps/vscode/src/services/uri/SharedUriHandler.ts`. Extension id is
`saoudrizwan.claude-dev`, so the URI is
`vscode://saoudrizwan.claude-dev/task?prompt=<urlencoded>` — reachable from bash via
`open` (macOS) or `code --open-url`. **This starts a Cline task with no human interaction, in
the VS Code extension.** Requires a visible webview.

There is also `/lg-task?prompt-file=…&webhook-url=…&webhook-token=…`, which reads a spec file
from disk, installs webhook hook scripts, and starts a task whose prompt tells the model to
re-read the file after compaction. That is, almost exactly, a headless "task file" entry point.
Added in v3.85.0 per `CHANGELOG.md`.

Version-gated: `TASK_URI_PATH` is **absent at v3.26.6, v3.35.0 and v3.50.0, present at
v3.70.0**. So it landed somewhere in v3.51–v3.70.

### Hooks (v3.36.0+)

Executable scripts named after the event, discovered in `~/Documents/Cline/Hooks`,
`~/.cline/hooks`, `<workspace>/.clinerules/hooks`, `<workspace>/.cline/hooks`. Extensions:
none, `.sh`, `.bash`, `.zsh`, `.js`, `.mjs`, `.cjs`, `.ts`, `.mts`, `.cts`, `.py`, `.ps1`.
Payload arrives as JSON on stdin; control is returned as JSON on stdout.

Events: `TaskStart`, `TaskResume`, `TaskCancel`, `TaskComplete`, `TaskError`, `PreToolUse`,
`PostToolUse`, `UserPromptSubmit`, `PreCompact`, `SessionShutdown`.
Source: `sdk/packages/core/src/hooks/hook-file-config.ts`. Documentation is thin —
<https://docs.cline.bot/customization/hooks> currently just points at `/sdk/plugins`.

Two facts that matter to your design:

- **`PreToolUse` and `PostToolUse` can inject context and can cancel.** A hook returning
  `{"context": "..."}` gets that text appended into the conversation (`appendContext`); a hook
  returning `{"cancel": true}` stops the run. Source: `hook-file-hooks.ts`,
  `afterToolResultFromControl` / the corresponding pre-tool mapper.
  **This is a genuine loop-glue lever**: a `PostToolUse` hook can append "3 questions still
  pending — claim the next one now" after every tool result, from outside the model's
  discretion. Upstream fixed the delivery of exactly this in a recent release ("Deliver a
  `PreToolUse` hook's `contextModification` to the model again, and wait for `PostToolUse`
  hooks so their output and `cancel` control are honored" — `CHANGELOG.md`), which tells you
  it was broken for a while. Verify before depending on it.
- **`TaskComplete` cannot keep the loop alive.** `agent_end` hooks run via
  `runAsyncHookCommands({ … detached: true })` — fire-and-forget, output ignored. Source:
  `hook-file-hooks.ts` `runTurnEnd`. It *can* fire an external process, so
  `TaskComplete` → shell script → `open "vscode://saoudrizwan.claude-dev/task?prompt=…"` is a
  viable **restart-after-death** watchdog, but it cannot prevent the death.

### Not headless

The VS Code commands (`cline.addToChat`, `cline.explainCode`, …) either only populate the input
box without submitting, or are only invocable from inside VS Code. There is no supported way to
execute a VS Code command from bash.

---

## 7. Open questions — measurable only inside your own build

Ordered by how much a wrong guess costs.

1. **Which upstream version did the fork branch from?** This one answer settles the request
   cap, hooks, the `/task` URI, `<explicit_instructions>` wrapping, and the bash timeout
   semantics. Check the extension's `package.json` version, or look for
   `auto_approval_max_req_reached` in the bundled JS.

2. **What is the bash tool timeout, and what does the model see when it fires?** The brief says
   it times out, which means the fork is either SDK-based or carries a local patch. Measure
   with `sleep 60; echo done` and read the tool result verbatim. The two possibilities lead to
   very different designs: *result returned to the model* (loop survives, poll freely) versus
   *task aborted* (every poll is a coin flip).

3. **Does a timed-out command get detached with a log path, or killed?** Determines whether
   long-poll option 2 in §5 is available or must be hand-rolled with `nohup`.

4. **Is the max-requests gate present, and what is its ceiling?** Try setting it to `999999` in
   the auto-approve menu and confirm it persists. Remember it only takes effect on a *new*
   task (<https://github.com/cline/cline/issues/4907>).

5. **Is `attempt_completion` reachable at all?** Ask the model in a scratch task to call it and
   see whether the task parks or auto-continues. If the fork auto-approves completion, the
   whole risk profile changes. If it parks — which I expect — then measure how many rounds a
   plainly-worded "never call attempt_completion" prohibition actually buys you. **This is the
   experiment that decides the prototype.**

6. **Does the workflow body survive truncation?** Run past the context window and check whether
   the loop instruction is still in the first user message. §4 says it should; the fork's
   truncation strategy could differ.

7. **Are hooks present, and does `PostToolUse` context injection actually reach the model?**
   Upstream broke and re-fixed this. If it works, it is a much stronger loop guarantee than
   prompt discipline. Test with a hook that echoes `{"context":"KEEP GOING"}` and check the
   transcript.

8. **How many auto-approved requests does one question-answer round actually cost?** Needed to
   size the cap and to decide between polling strategies. Expect 2–4; measure it.

9. **Does the fork's system prompt differ?** A proprietary build may have retuned the prompt
   toward or away from `attempt_completion`. If the bundle is readable, diff the system prompt
   against upstream's for the same version.

10. **What happens on a provider error mid-loop, with no human?** §4 says one automatic retry
    then a permanent park. Over a long run this is the most likely cause of silent death — so
    an external liveness check (last-modified time on the queue directory) plus a restart path
    is probably not optional.

---

## Source index

**Primary — Cline source (`github.com/cline/cline`)**

- `apps/vscode/src/core/prompts/responses.ts` — `noToolsUsed` continuation text
- `apps/vscode/src/sdk/slash-command-expansion.ts` — current workflow splicing
- `apps/vscode/src/shared/AutoApprovalSettings.ts` — max-requests now a dead legacy field
- `apps/vscode/src/services/uri/SharedUriHandler.ts` — `/task` and `/lg-task` URI routes
- `apps/vscode/src/services/lg-cns-integration/webhook-hooks.ts` — generated TaskStart / PostToolUse / TaskComplete hooks
- `apps/vscode/src/core/context/instructions/user-instructions/rule-helpers.ts` — `.clinerules/workflows`
- `sdk/packages/core/src/extensions/tools/executors/bash.ts` — 30 s default timeout, detach-on-timeout
- `sdk/packages/core/src/extensions/tools/definitions.ts` — timeout surfaced as a tool result
- `sdk/packages/core/src/hooks/hook-file-config.ts` — hook event names and search paths
- `sdk/packages/core/src/hooks/hook-file-hooks.ts` — hook control contract; `agent_end` is detached
- `CHANGELOG.md` — v3.35.0 auto-approve rework, v3.36.0 hooks, v3.85.0 `/lg-task`, v4.1.8 YOLO removal
- At tag `v3.26.6`: `src/core/task/index.ts`, `src/core/task/ToolExecutor.ts`,
  `src/core/task/tools/autoApprove.ts`, `src/core/slash-commands/index.ts`,
  `src/core/prompts/commands.ts`, `src/core/context/context-management/ContextManager.ts`,
  `src/integrations/terminal/TerminalProcess.ts`, `src/shared/AutoApprovalSettings.ts`,
  `webview-ui/src/components/chat/auto-approve-menu/AutoApproveModal.tsx`

**Primary — Cline docs and blog**

- <https://docs.cline.bot/features/auto-approve>
- <https://docs.cline.bot/customization/cline-rules>
- <https://docs.cline.bot/core-workflows/using-commands>
- <https://docs.cline.bot/cli/cli-reference>
- <https://docs.cline.bot/cli/scheduling>
- <https://docs.cline.bot/customization/hooks>
- <https://cline.bot/blog/stop-adding-rules-when-you-need-workflows>
- <https://cline.bot/blog/cline-3-13-toggleable-clinerules-slash-commands-previous-message-editing>

**Primary — issues**

- <https://github.com/cline/cline/issues/3480> — max requests causes task lockout
- <https://github.com/cline/cline/issues/4907> — max-requests change does not apply to the current task
- <https://github.com/cline/cline/issues/1612> — auto-approved counter not resetting

**Prior art**

- <https://ghuntley.com/ralph/> — the Ralph loop
- <https://www.theregister.com/2026/01/27/ralph_wiggum_claude_loops/>
- <https://github.com/abstractionlair/MultiModelCLIEmail> — Maildir bridge, `msg poll --wait`
- <https://dev.to/aviad_rozenhek_cba37e0660/communication-protocols-for-ai-agents-that-cant-talk-to-each-other-b23> — file-based inter-agent messaging, what failed
- <https://www.firecrawl.dev/blog/loop-engineering> — loop triggers and stop conditions
- <https://docs.warp.dev/agent-platform/local-agents/interacting-with-agents/prompt-queueing/> — prompt queueing semantics
