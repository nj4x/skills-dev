# Provenance marks in refactor-tests: token cost vs. behaviour impact

**Location:** `/Users/r.herasymenk/workspace/skills-dev/engineering/refactor-tests/reference/springboot.md`

## Executive Summary

Provenance marks (`[C]`, `[S]`, `[D]`, `[C2]`) appear 62 times in a 311-line reference file consumed by AI agents executing test refactoring. Cost: ~2% of file tokens on every load; behaviour impact: ~13% of marks gate agent actions. Verdict: **Drop all marks except `[D]` when it changes agent action**. Replace most with inline confidence hedges ("verify against your Spring version" vs. generic `[S]` tag); the few ~5 marks that explain why an action is mandatory should stay. Maintenance: the scheme binds to commit hashes in specific projects; it does not scale.

---

## Mark Census

**Counts (springboot.md, 311 lines, 62 total marks):**
- `[C]`: 28 marks — commit 2b0f6bf7 (reference Kotlin project)
- `[S]`: 20 marks — standard Spring/Boot documented behaviour  
- `[D]`: 9 marks — derived risk, requires verification
- `[C2]`: 5 marks — second project (federation), three commits

**Behaviour-changing vs. inert:**
- **Behaviour-changing** (gates or conditionally modifies action): ~8 marks (~13%)
  - `[D]` "Treat as a check to run, not a fact" (legend, line 15)
  - `[D]` "When a YAML switch appears to do nothing, this is the first thing to check" (Trap 1, line 240)
  - `[D]` "Never use `relaxed=true` in a shared base class" (C2.5, line 178)
  - `[D]` "Before flipping any switch, `rg` the test tree for assertions on the component" (C3, line 200)
  - `[C]` on "Escape hatch" at C3 explains production-safe override pattern (line 200)
  - `[C]` on "Only when" at C3 (annotation attribute required only if already declared, line 193)
  - `[C]` on BootstrapApplicationListener ordering—setter must be systemProperty not YAML (Trap 1, line 228)
  - `[S]` at legend & throughout: "Confirm against the project's Spring version before relying on it" (line 14)

- **Inert annotation** (~54 marks, ~87%): mark present but does not change how agent reads the sentence or what action follows.
  - Examples: "Two test classes with the **same key** share one context; two with **different keys** each pay a full application startup. `[S]`" — the agent learns the fact, the mark adds metadata about source; agent behaviour is unchanged.
  - Table entries tagging every row: most do not prescribe agent action.

---

## Analysis against writing-for-agents criteria

### Criterion: No-op test (does line change behaviour vs. default?)

**Default model capability:** Claude already assumes technical documentation is from high-trust sources (Spring/Gradle docs, reference projects). The mark scheme distinguishes evidence levels; the model does not change behaviour based on _whether_ a claim is evidenced, only whether the claim itself is true.

**Finding:** Most marks fail the no-op test. `[S]` at line 52 ("Spring's TestContext framework caches application contexts…") does not cause the agent to verify against Spring docs; the agent already assumes the statement is accurate.

**Exception:** `[D]` at line 15 ("Treat as a check to run, not a fact") explicitly gates behaviour — it signals the agent to treat that claim as a hypothesis to verify by running it.

### Criterion: Context load (tokens spent on every turn)

- Marks themselves: 4-5 tokens per instance (`[C]`, `[S2]`, etc.) × 62 instances = ~250 tokens.
- Legend table (lines 9–16): ~80 tokens, loaded once per context.
- Total: **~330 tokens per load**, or **~2% of file overhead**. Not catastrophic, but recurring.

### Criterion: Relevance and sediment

- The scheme was authored when only one project (2b0f6bf7) was evidence. Commit hash no longer points to a reachable repo for agents; it is dead metadata.
- `[C2]` added later (commits 410caa81, ba6120ce, f1af8222 in federation). These bindings are current and correct, but they scale poorly: every new project adding evidence requires a new mark type or a growing `[C2]` footnote.
- Over time, the scheme becomes a liability: stale commit hashes, proliferating mark types, yet the core claim (hypothesis vs. fact) does not become clearer to the agent.

### Criterion: Degree of freedom / specificity

The scheme is _weakly prescriptive_. It tags a claim but never says "ignore this" or "must verify before use." Only `[D]` and `[S]` legends carry conditional language:
- `[D]` → "treat as a check" (action implied: verify).
- `[S]` → "confirm against the project's Spring version" (action implied: run a lookup).

But these hedges are in the legend, not inlined. An agent may load springboot.md and miss the legend if it jumps to a specific section. Inline hedges are more reliable.

---

## External guidance findings

### Anthropic's skill-authoring best practices

**Source:** [Anthropic Platform Docs – Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)

Key principles:
1. **Conciseness**: "Once Claude loads SKILL.md, every token competes with conversation history and other context."
2. **No-op test**: Does the line change behaviour? If not, delete it.
3. **Single source of truth**: Duplication (same meaning in multiple places) costs tokens and maintenance.
4. **Control tuning**: Dial specificity to task fragility; high-specificity guidance is for brittle tasks, low for exploratory ones.

**Application:** The refactor-tests skill is medium-fragility (phases are sequential, gates are strict). A mark scheme adds specificity without adding constraint; it is a no-op. Inline hedges ("verify against your Spring version at deployment") are more specific and recoverable if the agent misses the legend.

### Skill-writing vocabulary from SKILL-MECHANICS.md

**Progressive disclosure** principle: Push reference behind pointers; keep the top legible. A 62-mark annotation scheme is static metadata, not a branch or branch condition — every mark is present on every read, whether relevant or not. This violates progressive disclosure.

**Leading words** principle: Repeated tokens that accumulate meaning accumulate _distributed_ meaning the model recruits from pretraining. `[D]`, `[C]`, etc., do not recruit pretraining — they are project-local symbols with fixed definitions. Every use must look up the legend, then interpret. By contrast, inline English ("verify before relying") recruits the model's pretraining on "verification" and "reliance," doubling the specificity with fewer tokens.

---

## Mark scheme scalability

**Current state:**
- `[C]`: one project, one commit.
- `[C2]`: added later; federation project, three commits. 
- Next project? `[C3]`? Or grow `[C2]` footnotes?

**The problem:** The scheme binds to _commits_, not _projects_. Commits move, get rebased, rot. Commit hashes are evidence pointers, not stable assertions. Once a commit is no longer reachable (merged, repo archived, internal project inaccessible), the mark becomes an opaque symbol with no grounding.

**Alternative:**  inline confidence levels without binding to projects.
- ✗ `[C2]` "this holds for federation (Spring Boot 3.5.8)"
- ✓ "this holds for Spring Boot 3.5.8+ (verify against your version)"

The second is project-agnostic, inline, and more directly constrains agent behaviour (agent knows _which version_ to verify against).

---

## Recommendation

### Decision: Drop all marks except `[D]` when behaviour-changing; replace inert marks with inline hedges.

**Concrete edits:**

1. **Delete the provenance legend** (lines 9–16, ~80 tokens). Replace with a single sentence: "All claims in this file assume Spring Boot 3.4+; verify against your version." Inline `[S]` marks become unnecessary.

2. **Inline confidence hedges for claims** that require verification:
   - Current: "Spring's TestContext framework caches application contexts keyed by configuration. `[S]`"
   - Revised: "Spring's TestContext framework caches application contexts keyed by configuration (Spring 5.4+; confirm against your version)."
   - Benefit: Agent knows exactly what to verify and against what.

3. **Keep `[D]` marks only where they gate action**:
   - Line 15 (legend): "Treat as a check to run, not a fact." → Keep.
   - Line 240 (Trap 1): "When a YAML switch appears to do nothing, this is the first thing to check." → Keep as `[D]` or inline as "If a switch appears inert, check this first—it's the most common cause `[D]`."
   - Line 178 (C2.5): "Never use `relaxed=true` in a shared base class." → Keep as a strong constraint.
   - Line 200 (C3): "Before flipping any switch, `rg` the test tree for assertions…" → Already strong; mark is redundant.

4. **Remove commit hash references** (2b0f6bf7, 410caa81, etc.) or replace with version bounds:
   - Current: "Evidenced by a real commit that applied it (`2b0f6bf7`, a Kotlin + Spring Boot + Gradle service)."
   - Revised: "Verified on Spring Boot 3.5.8, Gradle 8.x, Kotlin 1.9.x."

5. **Consolidate federation evidence**: The three federation commits are already in the codebase. Name them inline where they apply, not in a mark legend:
   - "To suppress this warning on JDK 21+, declare the byte-buddy agent explicitly (federation: commit 410caa81)."

**Expected outcome:**
- ~330 tokens saved on load (legend + 62 marks = ~2% file size reduction).
- Clarity: agent reads inline hedges and version constraints on first read, no legend lookup required.
- Maintainability: new projects add evidence inline ("verified on Spring Boot 4.0"); no new mark types.
- Compliance: aligns with Anthropic best practices (concise, no-ops removed, progressive disclosure respected).

**Acceptance test:** 
- An agent reading the revised file should never need to scroll to a legend.
- Every claim requiring verification should name what to verify against.
- The file should read like a technical reference for the agent, not a research paper with attribution marks.

---

## Sources

- [Anthropic Platform Docs – Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Platform.claude.com – Best practices for creating agent skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Anthropic CLAUDE.md (local: `/Users/r.herasymenk/.claude/skills/writing-for-agents/SKILL.md` and `SKILL-MECHANICS.md`)
- [Code.claude.com – Extend Claude with skills](https://code.claude.com/docs/en/skills)
