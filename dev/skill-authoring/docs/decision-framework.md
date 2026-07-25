# Decision Framework: Skill vs Rule vs Workflow

## Quick Decision Tree

```
Need to enforce consistent behavior always?
  → YES: Use RULE
  → NO: Continue

Need to automate repetitive tasks with a command?
  → YES: Use WORKFLOW
  → NO: Continue

Need on-demand, domain-specific knowledge?
  → YES: Use SKILL
  → NO: Consider MCP Server
```

## When to Use Each

### Rules

**Always active** - Enforce consistent behavior across all conversations.

**Use cases:**
- Coding standards (indentation, naming conventions)
- Technology stack preferences (use React, not Vue)
- Project structure conventions
- Security requirements (no hardcoded secrets)
- Testing standards (always write tests)
- Code review criteria

**Example Rule:**
```yaml
name: coding-standards
description: Enforce coding standards for this project. Always active.
```

### Workflows

**Invoked via command** - Automate repetitive, multi-step tasks.

**Use cases:**
- Component creation (scaffold React component with tests)
- Daily report generation
- PR template creation
- CI/CD pipeline updates
- Migration scripts
- Documentation generation

**Example Workflow:**
```yaml
name: create-react-component
description: Create a new React component with tests, styles, and TypeScript types. Invoke with /create-component
```

### Skills

**Loaded on-demand** - Provide domain-specific expertise for complex tasks.

**Use cases:**
- Complex multi-step workflows (deployment, database migrations)
- Domain-specific knowledge (API integration patterns)
- Specialized debugging (framework-specific issues)
- Architecture decisions (microservices, monolith)
- Platform-specific guidance (AWS, GCP, Azure deployment)
- Testing workflows (E2E test setup, performance testing)
- Code review checklists (team-specific standards)
- Database operations (schema evolution, rollback procedures)

**Example Skill:**
```yaml
name: aws-cdk-deploy
description: Deploy applications to AWS using CDK. Use when deploying, updating infrastructure, or managing AWS resources.
```

## Detailed Comparison

| Aspect | Rules | Workflows | Skills |
|--------|-------|-----------|--------|
| **When Active** | Always | When invoked via command | When matched by description |
| **Context Cost** | Always present (low) | When invoked (medium) | When matched (low) |
| **Best For** | Standards enforcement | Repetitive automation | Domain expertise |
| **Complexity** | Simple | Medium | High |
| **Flexibility** | Low (always on) | Medium (command-driven) | High (context-aware) |
| **Examples** | Coding standards, tech stack | Component creation, reports | Deployment, debugging |

## Decision Criteria

### Choose RULES when:

1. **Behavior must be consistent** - Every conversation should follow the same rules
2. **No conditional logic needed** - Apply uniformly regardless of context
3. **Low token cost is critical** - Rules are always active
4. **Standards enforcement** - Coding conventions, security policies, testing requirements

### Choose WORKFLOWS when:

1. **Task is repetitive** - You do it often with similar steps
2. **Command-based invocation** - User explicitly triggers it
3. **Deterministic steps** - Flow doesn't vary much based on context
4. **Automation focus** - Speed up routine tasks

### Choose SKILLS when:

1. **Domain-specific knowledge** - Complex workflows for specific domains
2. **Not always needed** - Only relevant for certain types of requests
3. **Context-dependent** - Steps may vary based on situation
4. **Complex instructions** - More detailed than Rules, but not always active
5. **Expert-level guidance** - Encode institutional knowledge from experienced developers

### Choose MCP SERVER when:

1. **External integration needed** - Connect to APIs, databases, cloud services
2. **Tools required** - Need executable functions, not just instructions
3. **Shared across projects** - Multiple developers access same functionality
4. **HTTP transport needed** - Remote server access required
5. **Complex logic** - Business logic that shouldn't be in instructions

## Example Scenarios

### Scenario 1: Code Style Enforcement

**Request:** "Make sure all code follows project conventions"

**Decision:** RULE
- Reasoning: Behavior must be consistent across all conversations
- Implementation: Simple rules about naming, formatting, structure

### Scenario 2: Create React Component

**Request:** "Create a new button component with tests"

**Decision:** WORKFLOW
- Reasoning: Repetitive task with deterministic steps, invoked explicitly
- Implementation: Multi-step process (create file, add imports, write tests, add styles)

### Scenario 3: AWS Deployment

**Request:** "Help me deploy this application to AWS"

**Decision:** SKILL
- Reasoning: Domain-specific knowledge, not always needed, context-dependent
- Implementation: Detailed guidance on CDK, IAM roles, infrastructure setup

### Scenario 4: Database Migration

**Request:** "I need to add a new column to the users table"

**Decision:** SKILL
- Reasoning: Complex multi-step process with rollback procedures, not always needed
- Implementation: Schema evolution strategy, testing approach, rollback plan

### Scenario 5: CI/CD Pipeline Update

**Request:** "Add automated testing to the GitHub Actions workflow"

**Decision:** WORKFLOW
- Reasoning: Repetitive task with clear steps, command-based invocation
- Implementation: Edit workflow file, add test jobs, configure triggers

### Scenario 6: Debug Flask Application

**Request:** "My Flask app is returning 500 errors"

**Decision:** SKILL
- Reasoning: Domain-specific debugging knowledge, not always needed
- Implementation: Flask-specific debugging steps, common error patterns, logging strategies

## Migration Guidance

### When to Move Between Types

**Rule → Skill**
- Rule is too complex and consuming too much context
- Rule should only apply in specific situations
- Rule needs conditional logic

**Workflow → Skill**
- Workflow steps vary significantly based on context
- Workflow is invoked via description matching, not commands
- Workflow needs more flexibility than deterministic steps

**Skill → Workflow**
- Skill is always triggered for common repetitive tasks
- Skill could benefit from command-based invocation
- Skill is actually simple automation, not domain knowledge

**Skill → MCP Server**
- Skill needs external API access
- Skill should provide executable tools
- Multiple developers need shared functionality

## Practical Examples from Real Projects

### Flow Development (Your Project)

**Current:** Skill
- **Why:** Complex domain knowledge about Flow Engine, not always needed
- **Content:** Node implementation, versioning strategies, testing protocols
- **Correct choice:** ✅ Domain-specific expertise for authentication flows

### If you added "Always use 4-space indentation"

**Recommended:** Rule
- **Why:** Behavior must be consistent across all conversations
- **Content:** Simple, unconditional standard
- **Correct choice:** ✅ Coding standard enforcement

### If you added "Generate flow node template"

**Recommended:** Workflow
- **Why:** Repetitive task with deterministic steps, command-based
- **Content:** Create node file, add imports, implement initialize() and processUserData()
- **Correct choice:** ✅ Automation of common task

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│  Always on? → YES → RULE                                      │
│  ↓ NO                                                        │
│  Repetitive automation? → YES → WORKFLOW                     │
│  ↓ NO                                                        │
│  Domain-specific expertise? → YES → SKILL                    │
│  ↓ NO                                                        │
│  External tools/APIs? → YES → MCP SERVER                      │
└─────────────────────────────────────────────────────────────┘
```

## Common Mistakes

❌ **Using Rules for complex workflows** → Consume too much context
✅ Use Skills instead, load on-demand

❌ **Using Workflows for domain expertise** → Can't adapt to context
✅ Use Skills for flexible, context-aware guidance

❌ **Using Skills for always-on standards** → Won't always trigger
✅ Use Rules for consistent behavior enforcement

❌ **Using Skills for external API access** → Can't execute tools
✅ Use MCP Servers for tools and API integration

## Summary

- **Rules**: Always-on standards (coding conventions, tech stack)
- **Workflows**: Command-based automation (component creation, reports)
- **Skills**: On-demand expertise (deployment, debugging, architecture)
- **MCP**: External tools and APIs (databases, cloud services, HTTP transport)

Choose based on:
1. **When it's active** (always vs invoked vs on-demand)
2. **Complexity** (simple vs medium vs high)
3. **Flexibility needs** (consistent vs deterministic vs context-aware)
4. **Context cost** (always present vs triggered per request)

When in doubt, start with the simpler option (Rule → Workflow → Skill) and upgrade as needed.