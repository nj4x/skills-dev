# Common Anti-Patterns and How to Fix Them

This document lists the most common mistakes developers make when creating Skills, with concrete examples and fixes.

## Anti-Pattern 1: Vague Descriptions

### The Problem
Using generic, non-specific descriptions that don't tell Cline when to trigger the skill.

### Bad Example
```yaml
---
name: aws-helper
description: Helps with AWS stuff.
---
```

### Why It Fails
- "Helper" is vague - doesn't specify what it actually does
- "AWS stuff" is too broad - doesn't trigger reliably
- No action verbs or trigger phrases
- Won't match specific user requests

### Good Example
```yaml
---
name: aws-cdk-deploy
description: Deploy applications to AWS using CDK. Use when deploying, updating infrastructure, or managing AWS resources.
---
```

### Why It Works
- Action verb: "Deploy"
- Specific domain: "AWS using CDK"
- Trigger phrases: "deploying, updating infrastructure, or managing AWS resources"
- Specific tool: "CDK"

### Fix Formula
1. Start with action verb (Deploy, Analyze, Generate, Configure)
2. Specify domain and tools
3. List trigger phrases users might say
4. Include file types or specific technologies

---

## Anti-Pattern 2: Overly Broad Descriptions

### The Problem
Trying to do too much in one skill, making it trigger for unrelated requests.

### Bad Example
```yaml
---
name: data-science
description: Analyze data, build models, deploy to production, manage databases, create visualizations, and write documentation for all data science projects.
---
```

### Why It Fails
- Covers too many domains (data analysis, ML, deployment, databases, docs)
- Will trigger for unrelated requests
- Instructions become unfocused and confusing
- Violates single responsibility principle

### Good Example
```yaml
---
name: data-analysis
description: Analyze CSV and Excel data files using pandas. Use when exploring datasets, generating statistics, or creating visualizations from tabular data.
---

name: ml-model-deployment
description: Deploy machine learning models to production. Use when packaging models, configuring endpoints, or setting up model serving infrastructure.
---
```

### Why It Works
- Split into focused, single-purpose skills
- Each has clear trigger criteria
- Instructions stay focused and actionable
- Users can activate exactly what they need

### Fix Strategy
- Split broad skills into multiple focused skills
- Each skill should have ONE primary purpose
- Use specific file types, tools, or domains

---

## Anti-Pattern 3: SKILL.md Too Long

### The Problem
Putting all content in SKILL.md, exceeding the 5k token limit.

### Bad Example
```
SKILL.md (10,000 tokens)
├── Section 1: Description (500 tokens)
├── Section 2: Basic concepts (1,000 tokens)
├── Section 3: Advanced concepts (2,000 tokens)
├── Section 4: Troubleshooting (2,000 tokens)
├── Section 5: Platform-specific guides (2,000 tokens)
├── Section 6: Examples (1,500 tokens)
└── Section 7: Reference material (1,000 tokens)
```

### Why It Fails
- Exceeds 5k token limit significantly
- All content loads even when not needed
- Slow initial load time
- Difficult to navigate

### Good Example
```
SKILL.md (3,000 tokens)
├── Core concepts (front-loaded)
├── Common workflows
├── References to supporting docs
└── Quick examples

docs/
├── advanced-concepts.md (1,000 tokens) - loads on-demand
├── troubleshooting.md (800 tokens) - loads on-demand
└── platform-specific.md (1,200 tokens) - loads on-demand
```

### Why It Works
- SKILL.md stays under 5k tokens
- Supporting docs load progressively
- Total context per session: Never exceeds 5k tokens
- Faster initial load

### Fix Strategy
- Front-load critical info in SKILL.md
- Move advanced topics to docs/
- Reference supporting docs from SKILL.md
- Only load docs when explicitly referenced

---

## Anti-Pattern 4: Abstract Concepts Only

### The Problem
Providing theoretical guidance without concrete examples.

### Bad Example
```markdown
## Error Handling

When errors occur, you should handle them appropriately. Consider the type of error and the context. Good error handling includes logging, user feedback, and recovery strategies.

Make sure to validate inputs before processing. Handle network errors gracefully. Provide clear error messages.
```

### Why It Fails
- Too abstract to follow
- No concrete code examples
- Doesn't show what "appropriate" looks like
- Cline can't implement based on vague guidance

### Good Example
```markdown
## Error Handling

Always wrap API calls in try-catch blocks:

```python
try:
    response = api_client.get_data()
except ConnectionError as e:
    log.error(f"Network error: {e}")
    return {"error": "Service unavailable"}
except TimeoutError as e:
    log.error(f"Request timeout: {e}")
    return {"error": "Request timed out"}
except APIError as e:
    log.error(f"API error: {e}")
    return {"error": "Invalid request"}

return {"data": response}
```

### Why It Works
- Concrete code example
- Shows specific error types to catch
- Demonstrates logging and error responses
- Cline can copy and adapt the pattern

### Fix Strategy
- Always provide concrete examples
- Show code, commands, or exact steps
- Include expected output
- Demonstrate both success and failure cases

---

## Anti-Pattern 5: Wrong File Naming

### The Problem
Naming conventions don't match the skill directory or use wrong case.

### Bad Example
```
AWS-Deploy/           # Wrong: PascalCase
└── SKILL.md

my_skill/            # Wrong: underscores
└── SKILL.md

skill-deployment/    # Wrong: directory name doesn't match skill name
└── SKILL.md
    name: "aws-deploy"  # Mismatch!
```

### Why It Fails
- Cline can't find the skill
- Naming conventions unclear
- Breaks automatic detection
- Confusing for other developers

### Good Example
```
aws-cdk-deploy/       # Correct: kebab-case
└── SKILL.md
    name: aws-cdk-deploy  # Matches directory name
```

### Why It Works
- Consistent naming convention
- Directory name matches skill name
- Easy to discover and use
- Follows established patterns

### Fix Strategy
- Use kebab-case (lowercase with hyphens)
- Name must match directory exactly
- Be descriptive about what the skill does
- Avoid: PascalCase, underscores, camelCase

---

## Anti-Pattern 6: Missing Trigger Phrases

### The Problem
Description doesn't include phrases users actually say.

### Bad Example
```yaml
---
name: database-migration
description: Database schema evolution and management for enterprise applications.
---
```

### Why It Fails
- No trigger phrases like "migrate", "add column", "update schema"
- Academic language ("schema evolution")
- Users say "I need to add a column" - won't trigger

### Good Example
```yaml
---
name: database-migration
description: Safely evolve database schemas. Use when adding columns, renaming tables, creating indexes, or performing migrations. Covers rollback procedures and testing strategies.
---
```

### Why It Works
- Trigger phrases: "adding columns, renaming tables, creating indexes, migrations"
- Matches how users actually talk
- Covers common operations
- Mentions testing and rollbacks

### Fix Strategy
- Listen to how users phrase requests
- Include common synonyms
- Mention specific operations
- Test with multiple phrasings

---

## Anti-Pattern 7: Not Testing Description

### The Problem
Writing a description and assuming it will work without verification.

### The Problem
```
Developer writes: "Manage AWS infrastructure"
Thinks: "User says 'deploy to AWS' → skill triggers"
Reality: Skill doesn't trigger because description is too vague
```

### Why It Fails
- Can't predict how Cline will match descriptions
- Words that seem synonymous may not match
- Only way to know is to test
- Wastes time debugging later

### Good Practice
```
1. Write description: "Deploy applications to AWS using CDK"
2. Test with 5 phrasings:
   - "Help me deploy to AWS" → ✅ Triggers
   - "Set up AWS infrastructure" → ✅ Triggers
   - "CDK deployment" → ✅ Triggers
   - "Cloud setup" → ❌ Doesn't trigger
   - "Infrastructure as code" → ✅ Triggers
3. Iterate until 4/5+ phrasings work
4. Add missing trigger phrases to description
```

### Why It Works
- Empirical verification of description quality
- Catches missing trigger phrases
- Ensures reliable triggering
- Provides confidence in the skill

### Fix Strategy
- Test description with 3-5 phrasings
- Check if skill triggers each time
- Add missing synonyms or phrases
- Iterate until reliability is >80%

---

## Anti-Pattern 8: Using Scripts When Instructions Are Better

### The Problem
Putting flexible workflows in scripts when they should be instructions.

### Bad Example
```bash
# scripts/deploy.sh - Too rigid for context-dependent deployment
#!/bin/bash
region="us-west-2"
environment="production"
stack_name="app-stack"

cdk deploy --region $region --context env=$environment $stack_name
```

### Why It Fails
- Hardcoded values (region, environment)
- Can't adapt to context
- Same script every time
- Doesn't handle edge cases

### Good Example
```markdown
## Deployment Workflow

Ask the user:
1. Which region? (default: us-west-2)
2. Which environment? (dev/staging/production)
3. Stack name?

Then run:
```bash
cdk deploy --region <region> --context env=<environment> <stack-name>
```

If deployment fails:
1. Check CloudFormation events for errors
2. Verify credentials are valid
3. Ensure all dependencies are deployed
4. Try again with --rollback-off if needed
```

### Why It Works
- Adapts to context (asks questions)
- Handles different scenarios
- Provides error recovery guidance
- Flexible enough for various use cases

### Fix Strategy
- Use scripts for: validation, deterministic operations, calculations
- Use instructions for: workflows that vary by context, decision-making, flexible processes

---

## Anti-Pattern 9: Over-Engineering Structure

### The Problem
Creating too many supporting files for a simple skill.

### Bad Example
```
simple-helper/
├── SKILL.md (300 tokens)
├── docs/
│   ├── setup.md (100 tokens) - same info as SKILL.md
│   ├── advanced.md (50 tokens) - not needed
│   ├── troubleshooting.md (30 tokens) - no edge cases
│   └── examples.md (200 tokens) - just repeats SKILL.md
├── examples/
│   ├── example1.md - redundant
│   └── example2.md - redundant
├── checklists/
│   └── checklist.md - unnecessary for simple skill
└── templates/
    └── template.md - not needed
```

### Why It Fails
- More complexity than value
- Fragmented information
- Hard to navigate
- SKILL.md could handle everything

### Good Example
```
simple-helper/
└── SKILL.md (300 tokens) - All content in one file
```

### Why It Works
- Simple and focused
- Easy to navigate
- All content in one place
- Appropriate complexity level

### Fix Strategy
- Simple skills: Just SKILL.md
- Moderate skills: SKILL.md + 1-2 docs/
- Complex skills: Full structure (docs/, examples/, checklists/, templates/)
- Match structure to complexity

---

## Anti-Pattern 10: Ignoring Token Budget

### The Problem
Not tracking or optimizing token usage.

### Bad Example
```
Developer writes 8,000 token SKILL.md
→ Loads slowly
→ Consumes too much context
→ Other content gets truncated
→ Performance degrades
```

### Why It Fails
- Violates 5k token limit
- Slow load times
- Wastes context budget
- Poor user experience

### Good Example
```
Token Budget Tracking:
├── Description field guidance: 1,200 tokens (40%)
├── Common workflows: 600 tokens (20%)
├── Scripts vs instructions: 450 tokens (15%)
├── Token management strategy: 450 tokens (15%)
└── Naming & structure: 300 tokens (10%)
└── Total: 3,000 tokens ✅
```

### Why It Works
- Stays under 5k token limit
- Fast loading
- Efficient context usage
- Better performance

### Fix Strategy
- Track token count for each section
- Prioritize content (front-load critical info)
- Split large content into docs/
- Use progressive loading

---

## Anti-Pattern 11: No Actionable Examples

### The Problem
Providing abstract guidance without showing what to do.

### Bad Example
```markdown
## Node Versioning

You should implement version-aware nodes for mobile applications. This ensures backward compatibility. Consider the @NodeImpl annotation and how it works.

Make sure to test different versions.
```

### Why It Fails
- Doesn't show code
- Doesn't explain @NodeImpl
- No concrete steps
- Cline can't implement from this

### Good Example
```markdown
## Node Versioning

Create versioned implementations for mobile apps using @NodeImpl:

```java
// Version 1 - Original implementation
@NodeImpl(nodeName = NodeNames.SIGN_IN_CONSENT, 
          channel = Channel.NATIVE, since = 1)
public class NativeSignInConsentV1Impl implements Node {
    @Override
    public NodeExecutionResult initialize(FlowContext context, FlowQuery query) {
        return resultProcessor.getUserInputRequiredResult(
            List.of(new Consents("termsAccepted").required().component())
        );
    }
}

// Version 2 - Enhanced implementation with GDPR compliance
@NodeImpl(nodeName = NodeNames.SIGN_IN_CONSENT, 
          channel = Channel.NATIVE, since = 2)
public class NativeSignInConsentV2Impl implements Node {
    @Override
    public NodeExecutionResult initialize(FlowContext context, FlowQuery query) {
        return resultProcessor.getUserInputRequiredResult(List.of(
            new Consents("termsAccepted").required().component(),
            new Consents("marketingConsent").optional().component(),
            new Consents("analyticsConsent").optional().component()
        ));
    }
}
```

Version resolution:
- App version 1 → Gets V1 implementation
- App version 2 → Gets V2 implementation
- App version 3 (no V3) → Gets V2 (floor match)
```

### Why It Works
- Complete code example
- Shows annotation syntax
- Demonstrates before/after
- Explains version resolution
- Cline can copy and adapt

### Fix Strategy
- Always provide complete examples
- Show both good and bad implementations
- Include code, commands, or exact steps
- Explain why the example is good

---

## Anti-Pattern 12: Wrong Tool Choice

### The Problem
Using Skills when Rules or Workflows would be better.

### Bad Example
```yaml
---
name: coding-standards
description: Enforce coding standards. Use when writing code, formatting, or reviewing.
---

# Coding Standards

Always use 4-space indentation. Follow PEP 8. Write docstrings for all functions...
```

### Why It Fails
- Coding standards should ALWAYS be active
- Skills load on-demand, won't trigger reliably
- Wastes context checking for standards
- Better as a Rule

### Good Example
```yaml
---
name: coding-standards
description: Enforce coding standards for this project. Always active.
rules:
  - Use 4-space indentation
  - Follow PEP 8
  - Write docstrings for all public functions
  - Max line length: 88 characters
```

### Why It Works
- Always active, no need to trigger
- Low context cost
- Consistent enforcement
- Appropriate tool choice

### Fix Strategy
- See [decision-framework.md](decision-framework.md) for guidance
- Always-on standards → Rules
- Repetitive automation → Workflows
- On-demand expertise → Skills
- External tools → MCP

---

---

## Anti-Pattern 13: Summarizing the Implementation in the Description

### The Problem
Writing how-the-skill-works content into the `description` frontmatter field.

### Bad Example
```yaml
---
name: data-extractor
description: Uses a Python script with BeautifulSoup to parse HTML tables, iterate over rows, and export as CSV. Handles malformed HTML with fallback parser.
---
```

### Why It Fails
- The description is loaded at every session start for every installed skill (~100 tokens each)
- Mechanism descriptions waste those tokens on information needed only during execution
- Worse: the model may read the description and follow its summary rather than loading the full body — effectively skipping the body's detailed instructions
- The description should answer "should I open this skill now?" not "what does this skill do internally?"

### Good Example
```yaml
---
name: data-extractor
description: Extract tabular data from saved HTML pages into CSV. Use when the user has downloaded HTML and needs the tables as structured data.
---
```

### Why It Works
- Trigger-only: describes when to invoke, not how it works
- Agent routes correctly on the conditions; full instructions are in the body

### Fix Strategy
- Read your description aloud. If it answers "how does this work?" rather than "when should I open this?" — rewrite it
- Strip all mechanism descriptions, tool names used internally, and step-by-step summaries
- Keep: domain, what it produces, and the triggering conditions

---

## Anti-Pattern 14: Reference Chaining Beyond One Level

### The Problem
Building a chain of references: SKILL.md → docs/a.md → docs/b.md → docs/c.md.

### Bad Example
```
SKILL.md
  → "For advanced config, see docs/advanced.md"
     docs/advanced.md
       → "For platform details, see docs/platforms.md"
          docs/platforms.md
            → "For edge cases, see docs/edge-cases.md"
```

### Why It Fails
- Agents may not traverse deep reference chains, especially under token pressure or latency
- The agent may load the first reference and never reach the actual content
- Each hop risks a partial load that breaks the workflow silently

### Good Example
```
SKILL.md
  → "For advanced config, see docs/advanced.md"
  → "For platform details, see docs/platforms.md"
  → "For edge cases, see docs/edge-cases.md"
```

### Why It Works
- All references are one hop from SKILL.md
- Agent can load any reference directly without traversal
- No content is ever unreachable

### Fix Strategy
- `docs/` files are leaf nodes — they must not reference other docs/ files
- If a docs/ file has grown to need sub-references, consolidate it into one file or restructure so SKILL.md points directly to each leaf

---

## Anti-Pattern 15: Re-Teaching What the Model Already Knows

### The Problem
Writing explanations of concepts the model already has from training: Python syntax, git basics, HTTP concepts, common library APIs.

### Bad Example
```markdown
## Using Python Lists

A Python list is a mutable, ordered sequence. To add an item:
```python
my_list.append(item)
```
To iterate:
```python
for item in my_list:
    print(item)
```
```

### Why It Fails
- Every line the model already knows is a token wasted
- Skills should encode institutional knowledge, not training-data knowledge
- The body grows bloated, key instructions are harder to find, and load time increases

### Good Example
```markdown
## Processing the Output

Iterate the result list and extract the `symbol` and `price` fields. Skip entries where `price` is None.
```

### Why It Works
- Assumes the model knows Python
- Encodes the domain-specific rule (which fields, what to skip)

### Fix Strategy
- Read every paragraph and ask: "Does the model already know this from training?"
- If yes, delete it. Only keep project-specific, domain-specific, or non-obvious behavior.

---

## Anti-Pattern 16: SKILL.md Duplicating `docs/` Content

### The Problem
Writing the same guidance in both SKILL.md and a docs/ reference file.

### Why It Fails
- When guidance changes, you update one file and forget the other — they diverge
- The agent may read the stale version and follow outdated instructions
- Tokens are wasted loading the same content twice

### Fix Strategy
- Pick one home for each piece of guidance: either SKILL.md (needed every invocation) or docs/ (needed occasionally)
- SKILL.md should reference docs/ with a one-liner; the content lives only in docs/
- Do a duplication audit before publishing: if a paragraph in SKILL.md appears verbatim or nearly verbatim in a docs/ file, delete one copy

---

## Anti-Pattern 17: Bundling Multiple Concerns in One Skill

### The Problem
A skill that handles design + planning + implementation + testing + deployment — a framework disguised as a skill.

### Bad Example
```yaml
---
name: full-feature-workflow
description: Complete workflow for new features: design, spec, code, test, deploy. Use for any new feature work.
---
```

### Why It Fails
- The description is so broad it triggers on everything
- When the agent only needs the testing step, it loads instructions for design and deployment too
- Changing the deployment process requires editing a file that also governs design
- Each concern has different fragility; bundling forces one rigidity level for all

### Good Example
```
skill: feature-design (triggers on "design", "spec", "architecture")
skill: feature-implementation (triggers on "implement", "build", "code")
skill: feature-testing (triggers on "test", "verify", "QA")
skill: feature-deploy (triggers on "deploy", "release", "ship")
```

### Why It Works
- Each skill triggers only when its concern is relevant
- Agent loads only what the task needs
- Concerns can evolve independently

### Fix Strategy
- If your skill has more than one primary purpose, split it
- Each skill should have one trigger domain and one body focus
- Composition is free: the agent loads multiple focused skills naturally

---

## Anti-Pattern 18: Hard-Coded Absolute Paths

### The Problem
Using absolute paths in skill bodies or scripts: `/home/user/projects/myapp`, `C:\Users\name\Documents\`.

### Why It Fails
- Skills are not portable — they work on one machine and break silently on others
- CI environments, other team members, and Docker containers all have different path structures
- A skill that works locally fails in production

### Good Example
Use relative paths from the project root:
```bash
# Bad
python /home/alice/projects/myapp/scripts/validate.py

# Good
python scripts/validate.py

# Or discover the path at runtime
python "$(git rev-parse --show-toplevel)/scripts/validate.py"
```

### Fix Strategy
- Grep your skills/ directory for `/home/`, `/Users/`, `C:\`, `/root/` — these are always wrong
- Replace with relative paths, `$(pwd)`, or `$(git rev-parse --show-toplevel)`

---

## Anti-Pattern 19: Missing or Vague Trigger Conditions

### The Problem
A description that names the domain but doesn't say when to fire.

### Bad Example
```yaml
description: Database migration helper for schema changes.
```

### Why It Fails
- Doesn't name what the user says to trigger it
- "Schema changes" is too vague — the agent may not match "I need to add a column"
- No trigger phrases = skills that never activate

### Good Example
```yaml
description: Safely evolve database schemas. Use when adding columns, renaming tables, creating indexes, running migrations, or writing rollback procedures.
```

### Fix Strategy
- Test description with 5 phrasings a user might say
- Target: 4/5 fire the skill
- Add missing trigger phrases from failed tests

---

## Anti-Pattern 20: Trusting Third-Party Skills Without Audit *(source-derived)*

### The Problem
Installing a skill from an unfamiliar source without reading it first.

### Why It Fails
- A skill body is executed with operator-level trust
- A malicious skill can steer agent behavior, exfiltrate data via instructions to include sensitive files in outputs, or run unexpected scripts
- Typosquatted skill names are a real vector (e.g. `git-helpr` vs `git-helper`)

### Fix Strategy
- Read the full body of any third-party skill before installing
- Audit `scripts/` for outbound network calls, writes outside the project root, or credential capture
- Verify the skill name is not similar to one you rely on
- Test in a sandbox environment first

For the full security checklist, see [third-party-security.md](third-party-security.md).

---

## Anti-Pattern 21: Persistent Artifacts Without a Load Guard *(medium-impact)*

### The Problem
Skills that write persistent state files (CONTEXT.md, decision logs) loaded unconditionally at every session start.

### Why It Fails
Persistent artifacts are loaded at every session start, not on demand — their token cost multiplies across all invocations and negates the progressive loading benefit. Without a size cap and conditional-load guard, a 500-token CONTEXT.md loaded 10 times silently costs 5k tokens — equal to the entire SKILL.md budget.

### Fix Strategy
- Impose a size cap on any persistent artifact (suggested: ≤200 tokens)
- Add a conditional-load guard: the skill body should check whether the artifact is relevant to the current task before loading it
- Prefer on-demand `docs/` references over always-loaded persistent files
- Periodically prune decision logs to keep them within the cap

```markdown
<!-- load-guard example: only read CONTEXT.md when task involves [domain] -->
```

---

## Summary Checklist

Avoid these anti-patterns by checking:

- [ ] Description is specific and actionable
- [ ] Description includes trigger phrases users say
- [ ] SKILL.md is under 5k tokens
- [ ] Concrete examples are provided (not just abstract concepts)
- [ ] Name uses kebab-case and matches directory
- [ ] Tested description with multiple phrasings
- [ ] Used scripts for deterministic ops, instructions for flexible workflows
- [ ] Structure matches complexity (simple skills don't need 10 docs files)
- [ ] Token budget is tracked and optimized
- [ ] Right tool choice (Skill vs Rule vs Workflow)
- [ ] Description contains only trigger conditions, not mechanism descriptions
- [ ] All docs/ references are one hop from SKILL.md (no chains)
- [ ] Skill body contains no re-teaching of model training knowledge
- [ ] No content duplicated between SKILL.md and docs/ files
- [ ] Skill has one primary concern (not bundled)
- [ ] No absolute paths in skill body or scripts/
- [ ] Description includes trigger phrases users will say
- [ ] Third-party skills audited before installation (see third-party-security.md)

By avoiding these anti-patterns, your skills will trigger reliably, load efficiently, and provide actionable guidance that Cline can follow.