---
name: tool-authoring
description: Audit and rewrite MCP tool definitions — descriptions, parameter schemas, error responses, annotations — so an LLM can make correct tool-selection and invocation decisions. Use when descriptions are passive, omit when-NOT-to-call guidance, mention server-config prerequisites the LLM can't set, restate param types, or fail to distinguish sibling tools. Use when asked to "audit tool descriptions", "rewrite tool descriptions", "improve MCP tool descriptions", or "fix tool descriptions".
argument-hint: "[path/to/server.py]"
disable-model-invocation: true
---

# tool-authoring

Audit and rewrite MCP tool definitions — descriptions, parameters, error responses, names, and annotations — so an LLM can make correct tool-selection and invocation decisions without guessing.

**Core principle: describe observable behavior, never server-config prerequisites.** The LLM cannot set an env var, flag, or startup config on a running server. Every prerequisite must be expressed as an error the caller will *observe in a response*, not a precondition it must satisfy.

## The four rules for tool descriptions

Every tool description must cover four things (Anthropic):

**1. What the tool does** — lead with the problem it solves, not what it returns.
- ✅ "Get the detailed summary of what a community cluster contains and how its entities relate"
- ❌ "Retrieves the detailed LLM-generated report for one community id"

**2. When to use it** — workflow position, ordering relative to sibling tools, prerequisites as observable errors.
- ✅ "After list_communities returns a community id you want to understand"
- ❌ "Requires ENTITY_EXTRACTION=true" — the LLM cannot set an env var on a running server

**3. When NOT to call it** — the case empirically missing from most tools (in one audit of 856 real MCP tools, 56% had unclear purpose). Steer away from wrong uses and toward the better sibling.
- ✅ "Do not use for exact symbol lookup — use search_entities instead"
- ✅ "Skip if you already have the id from a prior call"

**4. Caveats and limitations** — return shape, key fields, failure modes, and *what it does NOT return*.
- ✅ "Returns a text summary; does not include raw entity rows. May indicate the report is still building"
- ❌ Listing fields without saying when or why they appear

Write **3–4 sentences minimum** for non-trivial tools. Completeness wins over brevity. **Intern test** (OpenAI): if a new hire couldn't correctly call this tool from the description alone, it's incomplete.

Agent-level "which tool when" orchestration belongs in the *system prompt*. The tool description is the per-tool "what it does and how to call it" reference — keep the two from drifting.

## Rules for parameters

1. **Type-suffix ambiguous names** to cut hallucination: `user_id` not `user`, `customer_name` not `name`. Keep naming consistent across the whole server.
2. **State what it controls**, not restate its name. ✅ "Limit results to paths under these directories; omit to search all" ❌ "Filter directories"
3. **Make invalid states unrepresentable.** Replace two booleans that can conflict with a single enum. Describe each enum value's *effect* in the description, not just list values.
   - ✅ `mode`: "preview = count matches without deleting; delete = remove matched rows"
   - ❌ separate `preview: bool` + `delete: bool` (can both be true)
4. **Inline format examples only where the schema can't express usage** — `"YYYY-MM-DD"`, `"San Francisco, CA"`. Examples can be dropped under context pressure without significant performance loss (empirical ablation); don't pad every field.
5. **Keep it lean:** < 5 params, flat scalar types, no restating the type in prose ("provide the customer_id string" adds nothing).

## MCP tool fields and annotations

An MCP tool has: `name`, `title`, `description`, `inputSchema`, `annotations` (MCP spec).

| Field | Model sees it? | Purpose |
|---|---|---|
| `description` | Yes | The what/when/when-not/caveats reference (rules above) |
| `title` | No | Human UI label only — never put model-facing info here |
| `annotations` | No (drive client behavior) | Express *risk level* programmatically |

Annotations, their spec defaults, and client effect:

| Annotation | Default | Meaning | Client behavior |
|---|---|---|---|
| `readOnlyHint` | false | No side effects | May skip confirmation |
| `destructiveHint` | true | May delete/overwrite | Client shows a confirmation prompt |
| `idempotentHint` | false | Repeat calls are safe | Allows retry |
| `openWorldHint` | true | Touches external/unbounded systems | Scrutinize output |

`destructiveHint` is only meaningful when `readOnlyHint=false` (MCP spec) — don't set it on a read-only tool. **Rule: prose explains what/when/why; annotations express risk.** Don't duplicate — if `readOnlyHint=true`, don't also write "this tool is read-only" in the description. Annotations are *hints, not guarantees*; from untrusted servers they may lie, so clients shouldn't rely on them for security.

## Error responses are recovery instructions

An error is a chance for the model to self-correct, not a failure code. Return: **what went wrong + what was expected + an example of correct input.**

- ✅ "No orders found for customer_id=123. Use get_customer_details to verify the id first."
- ❌ "404 Not Found" / bare empty list / silent success

Return errors **inside the result object**, not as MCP protocol errors — the model only sees, and can only recover from, what lands in the result. For side-effect-only tools (`send_email`, `delete_record`) return a plain `"success"` / `"failure"` string so the model gets unambiguous feedback.

## Naming conventions

- **Namespace by service and resource:** `asana_projects_search`, `github_list_prs`, `slack_send_message`.
- Names must match `^[a-zA-Z0-9_-]{1,64}$`.
- Keep ~20–30 tools visible at once; beyond that, use tool routing or namespaces.
- Offer targeted `search_*` over thin `list_*` wrappers that dump everything — a scoped search saves the model from paging through irrelevant results.

## Anti-patterns

Quick-reference index — most rows compress a rule from the sections above into a symptom → fix pair.

| Anti-pattern | Why it fails | Fix |
|---|---|---|
| "Requires X=true" for a server env var | LLM can't set startup config on a running server | Observable error: "Returns feature_disabled if X is not enabled" |
| "Requires an indexed root" | Not actionable without the error | "Returns root_not_indexed if the root hasn't been indexed via index_codebase" |
| Passive opener "Retrieves / Returns / Gets X" | Describes output, not the problem solved | Lead with the use case: "Find X before calling Y" |
| Omitting "when NOT to call" | Model misroutes to the wrong sibling (56% of audited tools had unclear purpose) | State the wrong uses and the better alternative |
| Two conflicting booleans | Model can produce an invalid state | Single enum making invalid states unrepresentable |
| Restating the param type ("the customer_id string") | Zero new information | State what the value *controls* and its effect |
| `"404"` / bare empty list on error | Model can't recover | Return what failed + expected + a correct example |
| Duplicating annotation info in prose | Redundant tokens, can contradict | Let `readOnlyHint`/`destructiveHint` carry risk; prose carries what/when |
| Thin `list_*` API wrapper | Dumps everything, floods context | Offer a targeted `search_*` |

## Workflow

### 1. Locate the target
Accept the file path as an argument. If none, search: `fd -e py server.py` or grep for `@app.tool` / `@mcp.tool` / `@_tool`.

### 2. Audit
For each tool-decorated function read its docstring, every `Field(description=...)`, its error paths, and its annotations. Score against the four rules, the parameter rules, and error design. Emit a violations table:

| Tool / Parameter | Violation type | Offending text |
|---|---|---|
| `get_community_report` | Server-config prerequisite | "Requires ENTITY_EXTRACTION=true" |
| `clear_index` | Conflicting booleans | `preview` + `delete` |
| `include_content_scan` | No effect described | "Whether to scan content" |

### 3. Propose rewrites
Draft a replacement satisfying all four rules; convert conflicting booleans to enums; make errors recovery-oriented; move risk signals to annotations. Show old → new inline. Optionally run `/critic` on the proposals before applying, or review them manually if critic is not installed.

### 4. Apply and verify
Apply each rewrite as an `Edit` targeting the unique old string. Then run the target project's compile + test checks, e.g.:
```sh
uv run python -m compileall -f server.py   # or the target project's equivalent
uv run --extra dev pytest                  # full suite, or the target project's equivalent
```
Commit when green.

## Quick checklist

- [ ] Every description covers all four: what it does, when to use, **when NOT to call**, caveats/limitations (incl. what it does *not* return)
- [ ] Non-trivial descriptions are 3–4 sentences and pass the intern test
- [ ] No description tells the LLM to set an env var or flag — use observable errors instead
- [ ] Agent-level orchestration lives in the system prompt, not the tool description
- [ ] Ambiguous param names carry a type suffix (`user_id`, not `user`); naming is consistent server-wide
- [ ] No two booleans can conflict — invalid states are unrepresentable via enums
- [ ] Enum/boolean descriptions state each value's *effect*; format examples only where the schema can't express usage
- [ ] < 5 flat scalar params; no prose restating a param's type
- [ ] Errors return what went wrong + expected + a correct example, inside the result object
- [ ] Side-effect-only tools return a plain success/failure string
- [ ] Risk is carried by `readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`, not duplicated in prose
- [ ] Tool names namespace service + resource and match `^[a-zA-Z0-9_-]{1,64}$`
