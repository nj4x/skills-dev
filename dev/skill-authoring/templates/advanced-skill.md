---
name: YOUR-SKILL-NAME
description: [ACTION VERB] [SPECIFIC DOMAIN] using [SPECIFIC TOOLS]. Use when [TRIGGER PHRASE 1], [TRIGGER PHRASE 2], or [TRIGGER PHRASE 3]. Covers [ADVANCED TOPIC 1], [ADVANCED TOPIC 2], and [ADVANCED TOPIC 3].
---

# Skill Name

## Overview

[Brief 1-2 sentence description of what this skill does]

## When to Use This Skill

This skill activates when you need to:
- [Specific task 1]
- [Specific task 2]
- [Specific task 3]

## Quick Start

Need to get started fast? Follow these 3 steps:

1. **[Quick Step 1]** - [Brief description]
2. **[Quick Step 2]** - [Brief description]
3. **[Quick Step 3]** - [Brief description]

For detailed guidance, see the relevant docs below.

---

## Core Concepts

### [Concept 1]
[Brief explanation]

For advanced details, see [docs/advanced-concept-1.md](docs/advanced-concept-1.md)

### [Concept 2]
[Brief explanation]

For advanced details, see [docs/advanced-concept-2.md](docs/advanced-concept-2.md)

---

## Common Workflows

### Workflow 1: [Workflow Name]

[Brief description of when to use this workflow]

**Steps:**
1. [Step 1 with details]
2. [Step 2 with details]
3. [Step 3 with details]

**See:** [docs/workflow-1.md](docs/workflow-1.md) for complete guide

### Workflow 2: [Workflow Name]

[Brief description of when to use this workflow]

**Steps:**
1. [Step 1 with details]
2. [Step 2 with details]
3. [Step 3 with details]

**See:** [docs/workflow-2.md](docs/workflow-2.md) for complete guide

---

## Examples

### Example 1: [Task Description]

**Request:** [User's request]

**Process:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Outcome:** [Result]

**Full code:** [examples/example-1.md](examples/example-1.md)

### Example 2: [Task Description]

**Request:** [User's request]

**Process:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Outcome:** [Result]

**Full code:** [examples/example-2.md](examples/example-2.md)

---

## Key Patterns

- ✅ **Good Pattern:** [Description with example]
  ```python
  # Good example code
  ```

- ❌ **Avoid:** [Anti-pattern description]
  ```python
  # Bad example code
  ```

---

## Common Issues

**Issue:** [Problem description]

**Solution:**
1. [Step 1]
2. [Step 2]

**See:** [docs/troubleshooting.md](docs/troubleshooting.md) for more issues

---

## Advanced Topics

For complex scenarios, see:

- **[Advanced Topic 1]** - [docs/advanced-topic-1.md](docs/advanced-topic-1.md)
- **[Advanced Topic 2]** - [docs/advanced-topic-2.md](docs/advanced-topic-2.md)
- **[Advanced Topic 3]** - [docs/advanced-topic-3.md](docs/advanced-topic-3.md)

---

## Testing

### Pre-Publish Checklist

Before publishing changes, run [checklists/pre-publish-checklist.md](checklists/pre-publish-checklist.md)

### Test Coverage

- Unit tests: See [examples/unit-tests/](examples/unit-tests/)
- Integration tests: See [examples/integration-tests/](examples/integration-tests/)

---

## Quick Reference

| Task | Command | Docs | Notes |
|------|---------|------|-------|
| [Task 1] | [Command] | [docs/link.md] | [Notes] |
| [Task 2] | [Command] | [docs/link.md] | [Notes] |
| [Task 3] | [Command] | [docs/link.md] | [Notes] |

---

## Reference Materials

- **API Documentation:** [docs/api-reference.md](docs/api-reference.md)
- **Configuration Guide:** [docs/configuration.md](docs/configuration.md)
- **Best Practices:** [docs/best-practices.md](docs/best-practices.md)

---

## Templates

Use these templates to accelerate development:

- **[Template 1]:** [templates/template-1.md](templates/template-1.md)
- **[Template 2]:** [templates/template-2.md](templates/template-2.md)

---

## Directory Structure

```
your-skill-name/
├── SKILL.md                    # This file (main guide)
├── docs/                       # Detailed documentation
│   ├── advanced-concept-1.md   # Loads on-demand
│   ├── advanced-concept-2.md   # Loads on-demand
│   ├── workflow-1.md           # Complete workflow guide
│   ├── workflow-2.md           # Complete workflow guide
│   ├── troubleshooting.md      # Common issues and fixes
│   ├── advanced-topic-1.md     # Complex scenarios
│   ├── advanced-topic-2.md     # Complex scenarios
│   ├── advanced-topic-3.md     # Complex scenarios
│   ├── api-reference.md        # API documentation
│   ├── configuration.md        # Configuration guide
│   └── best-practices.md       # Best practices
├── examples/                   # Complete code examples
│   ├── example-1.md            # Full working example
│   ├── example-2.md            # Full working example
│   ├── unit-tests/             # Unit test examples
│   └── integration-tests/      # Integration test examples
├── checklists/                 # Quality verification
│   └── pre-publish-checklist.md # Verify before publishing
└── templates/                  # Boilerplate code
    ├── template-1.md           # Starting template
    └── template-2.md           # Starting template
```

---

## Token Budget

SKILL.md stays under 5,000 tokens. Supporting docs load progressively.

| Section | Tokens | Notes |
|---------|--------|-------|
| Overview | 100 | Front-loaded |
| When to Use | 200 | Front-loaded |
| Quick Start | 150 | Front-loaded |
| Core Concepts | 800 | Brief, link to docs |
| Common Workflows | 1,000 | 2-3 workflows with links |
| Examples | 1,200 | 1-2 examples with links |
| Key Patterns | 600 | Front-loaded |
| Common Issues | 400 | Brief, link to docs |
| Advanced Topics | 200 | Links only |
| Testing | 150 | Links to checklists |
| Quick Reference | 300 | Front-loaded |
| **TOTAL** | **5,100** | **Over limit** |

**Adjustment:** Reduce Examples section to 1,000 tokens
**New Total:** 4,900 tokens ✅

---

## Template Usage Instructions

### 1. Replace Placeholders

Search and replace these placeholders in SKILL.md:
- `YOUR-SKILL-NAME` → Your skill name (kebab-case)
- `[ACTION VERB]` → Deploy, Analyze, Generate, Configure
- `[SPECIFIC DOMAIN]` → AWS using CDK, CSV files with pandas, etc.
- `[SPECIFIC TOOLS]` → CDK, pandas, JUnit, etc.
- `[TRIGGER PHRASE 1, 2, 3]` → Phrases users might say
- `[ADVANCED TOPIC 1, 2, 3]` → Complex topics covered in docs/

### 2. Create Directory Structure

```
mkdir -p your-skill-name/docs
mkdir -p your-skill-name/examples
mkdir -p your-skill-name/checklists
mkdir -p your-skill-name/templates
```

### 3. Create Supporting Files

Create files for:
- **docs/**: Advanced concepts, workflows, troubleshooting
- **examples/**: Complete code examples, tests
- **checklists/**: Quality verification checklists
- **templates/**: Boilerplate code

### 4. Fill in SKILL.md

Complete each section with specific content
- Keep it under 5,000 tokens
- Reference supporting docs from SKILL.md
- Front-load critical information

### 5. Token Budget Tracking

Track tokens for each section:
```python
import tiktoken
enc = tiktoken.encoding_for_model("gpt-4")
text = open("SKILL.md").read()
tokens = enc.encode(text)
print(f"Token count: {len(tokens)}")
```

### 6. Progressive Loading Strategy

- SKILL.md: Front-load critical info (~3k tokens)
- docs/: Load only when referenced (~1k each)
- examples/: Load only when referenced (~500-1k each)
- Total context per session: Never exceeds 5k tokens

### 7. Testing

Test description with 5 phrasings:
1. Most direct phrasing
2. Slightly different wording
3. Synonyms
4. Short/casual
5. Unrelated edge case (should NOT trigger)

Success criteria: 4/5+ phrases trigger (≥ 80%)

### 8. Quality Check

Before publishing:
- [ ] Description is specific and actionable
- [ ] Name uses kebab-case
- [ ] SKILL.md under 5k tokens
- [ ] Concrete examples provided
- [ ] Tested with multiple phrasings
- [ ] Token budget tracked
- [ ] Supporting docs load correctly
- [ ] All references are accurate

Run [checklists/pre-publish-checklist.md](../checklists/pre-publish-checklist.md) for complete verification.

---

## Example: Advanced Skill Structure

```
aws-cdk-deploy/
├── SKILL.md                          # Main guide (3k tokens)
├── docs/
│   ├── deployment-workflow.md        # Complete deployment guide
│   ├── infrastructure-types.md        # VPC, EC2, Lambda, etc.
│   ├── iam-roles.md                  # IAM role configuration
│   ├── troubleshooting.md             # Common deployment issues
│   ├── multi-environment.md          # Dev/staging/prod setup
│   ├── best-practices.md             # Security, cost optimization
│   └── configuration.md              # CDK configuration options
├── examples/
│   ├── simple-lambda.md              # Basic Lambda deployment
│   ├── vpc-ec2-app.md                # VPC + EC2 + Application
│   ├── serverless-api.md             # API Gateway + Lambda
│   ├── unit-tests/
│   │   └── lambda-test.md
│   └── integration-tests/
│       └── deployment-test.md
├── checklists/
│   └── pre-deploy-checklist.md       # Verify before deployment
└── templates/
    ├── lambda-stack.md               # Lambda stack template
    ├── vpc-template.md               # VPC template
    └── app-template.md               # Application template
```

**Progressive Loading:**
- SKILL.md loads (always) → 3,000 tokens
- User asks about VPC → docs/infrastructure-types.md loads → 800 tokens
- User wants example → examples/vpc-ec2-app.md loads → 1,000 tokens
- Total context: 4,800 tokens ✅

---

## Key Differences from Minimal Template

| Aspect | Minimal Template | Advanced Template |
|--------|------------------|-------------------|
| **Complexity** | Simple skills | Complex domains |
| **SKILL.md** | All content in one file | References supporting docs |
| **Token Budget** | 5k tokens | 3k in SKILL.md, rest in docs/ |
| **Structure** | Single file | Full directory structure |
| **Examples** | Embedded in SKILL.md | Separate files in examples/ |
| **Documentation** | Brief sections | Detailed docs/ |
| **Testing** | Mentioned in text | Separate examples/unit-tests/ |
| **Templates** | Not included | templates/ directory |
| **Checklists** | Not included | checklists/ directory |
| **Use Case** | Single-purpose skills | Multi-workflow domains |

---

**For more guidance, see:**
- [SKILL.md](../SKILL.md) - Complete skill authoring guide
- [checklists/pre-publish-checklist.md](../checklists/pre-publish-checklist.md) - Quality verification
- [docs/decision-framework.md](../docs/decision-framework.md) - Tool selection guidance
- [docs/common-anti-patterns.md](../docs/common-anti-patterns.md) - Mistakes to avoid
- [docs/testing-protocol.md](../docs/testing-protocol.md) - Testing methodology