---
name: skill-authoring
description: Guide for creating effective Cline Skills. Use when writing a new skill, improving an existing skill, debugging skill triggering issues, or deciding between Skills, Rules, and Workflows. Includes token optimization strategies, description best practices, testing protocols, and anti-patterns to avoid.
disable-model-invocation: true
---

# Skill Authoring Guide

## The Most Important Thing: The Description Field

The `description` in your SKILL.md frontmatter determines when Cline activates your skill. A vague description means your skill won't trigger when users expect it to.

### Good Descriptions (Specific & Actionable)

```yaml
description: Deploy applications to AWS using CDK. Use when deploying, updating infrastructure, or managing AWS resources.

description: Generate release notes from git commits. Use when preparing releases, writing changelogs, or summarizing recent changes.

description: Analyze CSV and Excel data files. Use when exploring datasets, generating statistics, or creating visualizations from tabular data.
```

### Weak Descriptions (Too Vague)

```yaml
description: Helps with AWS stuff.

description: Data analysis helper.

description: Useful for releases.
```

### Description Writing Formula

1. **Start with action verb**: Deploy, Analyze, Generate, Configure
2. **Specify the domain**: AWS using CDK, CSV and Excel files, git commits
3. **List trigger phrases**: "Use when deploying, updating infrastructure, or managing AWS resources"
4. **Include file types/tools**: CSV, Excel, Terraform, Docker, pandas
5. **Keep it under 1024 characters**

## Naming Conventions

The skill name (in `name` field and directory name) must match exactly.

**Good names (descriptive, kebab-case):**
- `aws-cdk-deploy`
- `pr-review-checklist`
- `database-migration`
- `api-client-generator`

**Avoid:**
- `aws` (too vague)
- `my_skill` (underscores)
- `DeployToAWS` (PascalCase)
- `misc-helpers` (too generic)

## Front-Load Critical Information

Cline reads SKILL.md sequentially. Put the most important content first:

1. Core concepts (description, naming)
2. Common workflows
3. Error handling
4. Advanced configuration

Use clear section headers so Cline can scan: `## Error Handling`, `## Configuration`, `## Testing`

## Two Kinds of Skills

Before writing a skill, name the bottleneck. Two types exist:

**Pattern A — capability primitives.** A thin wrapper over a deterministic CLI or script. Logic lives in code; the agent orchestrates calls. Typically 30–80 lines. Choose when the bottleneck is "the agent _can't_ do X." Examples: email sender, search tool, API-access wrapper, browser-automation driver.

**Pattern B — process primitives.** Encodes a methodology the agent follows. Pure prompt engineering — no scripts needed. Choose when the bottleneck is "the agent's output quality or process is bad." Examples: code-review discipline, TDD workflow, design-alignment process.

A mature setup uses both. These are not competing styles: capability primitives give the agent better tools; process primitives give it better methods. Decide the pattern first, then write the skill.

For worked examples and a decision tree, see [design-philosophy.md](docs/design-philosophy.md).

**Note:** Pattern A/B is a separate axis from instruction rigidity (see `### Match Rigidity to Fragility` below).

## Scripts vs Instructions

### When to Use Scripts (deterministic operations)

- Validation (linting configs, checking prerequisites)
- Data processing (parsing, formatting, transforming)
- Complex calculations (cost estimation, resource sizing)
- API interactions (fetching data, running health checks)

**Benefit**: Only script output enters context, not the code itself. A 500-line validation script produces simple "Passed" or error messages.

### When to Use Instructions (flexible guidance)

- Decision-making workflows
- Steps that vary by situation
- Best practices and patterns
- Anything requiring context-aware adaptation

### Match Rigidity to Fragility

Scale instruction rigidity to the cost of getting a step wrong:

- **Brittle, high-stakes steps** (destructive operations, irreversible sequences, security boundaries): use rigid, numbered steps with explicit checks. Over-specify rather than under-specify.
- **Robust, low-stakes steps** (text generation, analysis, summarization): use loose intent statements. Let the agent exercise judgment.

Over-rigidity on a forgiving task wastes tokens and suppresses useful agent initiative. Under-rigidity on a fragile task causes failures. Give one concrete check: if getting this step wrong would require manual recovery or cause data loss, make the instructions rigid.

### Check State Before Acting

For non-idempotent or destructive actions, instruct the agent to verify current state before acting and branch on the result:

```
Before creating X, check whether X already exists:
  → If it does: [update / skip / ask the operator]
  → If it doesn't: proceed with creation
```

This prevents duplicate work and destructive re-runs. Every mutating step in a skill body should have a pre-condition check.

## Token Management Strategy

### Core Principle: Keep SKILL.md Under 5k Tokens

If your skill needs more content, split it into supporting files in `docs/` and reference them only when needed.

### Progressive Loading — Three Levels

Skills load in three stages; each stage pays its token cost only when needed:

```
Level 1 — Description (~100 tokens, loaded at every session start for routing)
  Only the name + description are injected into context on startup.
  Dozens of skills can be installed with negligible overhead.

Level 2 — SKILL.md body (<5k tokens, loaded only on invocation)
  The full skill body loads when the description matches the user's request.
  This is what you write; keep it lean.

Level 3 — docs/ files and scripts (unbounded, loaded only when referenced)
  Referenced files load only when the SKILL.md body explicitly directs the agent to them.
  No token cost until accessed.
```

Design rule: push depth downward. Put in SKILL.md only what the agent needs on every invocation. Move everything else to `docs/`.

Keep `docs/` references one level deep — SKILL.md should link directly to each reference file. Never build chains (SKILL.md → a.md → b.md → c.md); agents may not follow deep chains under latency or token pressure.

## Skill Structure

```
my-skill/
├── SKILL.md              # Required: main instructions (≤ 5k tokens)
├── docs/                 # Optional: detailed documentation
│   ├── advanced.md       # Loads only when referenced
│   └── troubleshooting.md
├── examples/             # Optional: before/after comparisons
│   ├── good-example.md
│   └── bad-example.md
├── checklists/           # Optional: quality gates
│   └── pre-publish.md
└── templates/            # Optional: starter templates
    └── minimal.md
```

### Optional Frontmatter Fields

Beyond `name` and `description`, skills support:

- **`disable-model-invocation: true`** — Prevents auto-invocation. The skill only runs when explicitly called (e.g. `/skill-name`). Use for destructive operations, expensive workflows, or human-in-the-loop gates. **Limitation:** Some clients (Claude Code, open bug as of this writing) still inject the `description` into context even with this flag set — the flag reliably prevents *auto-invocation* but may not save discovery-level tokens. Keep descriptions terse regardless.

## Bundling Supporting Files

### docs/ (Information that's too detailed for SKILL.md)

- Advanced configuration options
- Troubleshooting guides for edge cases
- Reference material (API schemas, database schemas)
- Platform-specific instructions

**Usage**: Reference from SKILL.md: `See [advanced.md](docs/advanced.md) for complex configurations`

### examples/ (Before/after comparisons)

- Concrete examples of good vs bad implementations
- Real-world case studies
- Anti-patterns with fixes

**Usage**: Show transformation from vague to specific descriptions

### checklists/ (Quality verification)

- Pre-publish checklists (7-step quality gates)
- Description audit rubrics (scoring 0-10)
- Token budget estimators

**Usage**: Actionable verification before shipping

### templates/ (Starting points)

- `minimal-skill.md` - Simple skills with just SKILL.md
- `advanced-skill.md` - Skills with docs/scripts structure

**Usage**: Provide boilerplate to accelerate development

**New reference docs in this skill:**
- [design-philosophy.md](docs/design-philosophy.md) — Pattern A vs Pattern B decision tree and worked examples
- [authoring-workflow.md](docs/authoring-workflow.md) — End-to-end skill authoring process
- [composition-patterns.md](docs/composition-patterns.md) — How to design skills that work together
- [third-party-security.md](docs/third-party-security.md) — Security checklist for skills that install or execute third-party code

## Testing Your Skill

1. **Write description** and test 3-5 phrasings of the same request
2. **Verify skill triggers** in Cline when expected
3. **Check instructions are followed** correctly
4. **Confirm token budget** is reasonable (< 5k for SKILL.md)
5. **Test edge cases** and verify behavior

For detailed testing methodology, see [testing-protocol.md](docs/testing-protocol.md).

## Choosing the Right Tool

Not sure if you need a Skill, Rule, or Workflow? See [decision-framework.md](docs/decision-framework.md) for a systematic approach.

## Common Anti-Patterns

For a comprehensive list of mistakes and how to fix them, see [common-anti-patterns.md](docs/common-anti-patterns.md).

Quick examples:
- ❌ Description: "Helps with X" → ✅ Be specific: "Deploy X using Y. Use when Z"
- ❌ SKILL.md: 2000 lines → ✅ Split into docs/, keep < 5k tokens
- ❌ Abstract concepts only → ✅ Include concrete examples with code

For skills that install or execute third-party code, follow [docs/third-party-security.md](docs/third-party-security.md).

## Quick Reference Checklist

Before publishing a skill:

- [ ] Description is specific (no vague terms like "helps with")
- [ ] Description includes trigger phrases users might say
- [ ] Name uses kebab-case and matches directory name
- [ ] SKILL.md is under 5k tokens
- [ ] Critical info is front-loaded
- [ ] Concrete examples are included
- [ ] Tested with multiple phrasings of requests

For a complete pre-publish checklist, see [checklists/pre-publish-checklist.md](checklists/pre-publish-checklist.md).

## Getting Started Templates

Use these templates to accelerate development:

- **Minimal skill**: [templates/minimal-skill.md](templates/minimal-skill.md) - Simple skills with just SKILL.md
- **Advanced skill**: [templates/advanced-skill.md](templates/advanced-skill.md) - Skills with docs/scripts structure
