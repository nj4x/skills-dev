# Before: Vague Description Examples

These examples show common mistakes in skill descriptions that result in poor triggering.

## Example 1: AWS Deployment

```yaml
---
name: aws-helper
description: Helps with AWS stuff.
---

# AWS Helper

This skill helps with AWS deployments and infrastructure management.
```

### Problems
- ❌ "Helper" is vague - doesn't specify what it actually does
- ❌ "AWS stuff" is too broad - won't trigger reliably
- ❌ No action verbs
- ❌ No trigger phrases
- ❌ No specific tools mentioned (CDK, Terraform, etc.)

### Expected Trigger Rate: < 20%
```
"Deploy to AWS" → ❌ Won't trigger
"Set up infrastructure" → ❌ Won't trigger
"CDK deployment" → ❌ Won't trigger
"Cloud setup" → ❌ Won't trigger
```

---

## Example 2: Data Analysis

```yaml
---
name: data-skill
description: Data analysis helper.
---

# Data Analysis

Use this skill when working with data.
```

### Problems
- ❌ "Helper" is vague
- ❌ "Data analysis helper" is generic
- ❌ No file types mentioned (CSV, Excel, JSON)
- ❌ No tools mentioned (pandas, numpy)
- ❌ No specific use cases (visualization, statistics, cleaning)

### Expected Trigger Rate: < 30%
```
"Analyze sales_data.csv" → ❌ Won't trigger
"Create visualizations" → ❌ Won't trigger
"Data cleaning" → ❌ Won't trigger
```

---

## Example 3: Database Migration

```yaml
---
name: db-migrate
description: Database schema evolution and management for enterprise applications.
---

# Database Migration

For managing database schemas.
```

### Problems
- ❌ Academic language ("schema evolution")
- ❌ No trigger phrases like "migrate", "add column", "update schema"
- ❌ "Enterprise applications" is too broad
- ❌ Users say "I need to add a column" - won't trigger

### Expected Trigger Rate: < 25%
```
"Add a column to users table" → ❌ Won't trigger
"Migrate database schema" → ❌ Won't trigger
"Update table structure" → ❌ Won't trigger
```

---

## Example 4: Testing

```yaml
---
name: testing
description: Testing assistance for software development projects.
---

# Testing

Help with writing tests and testing strategies.
```

### Problems
- ❌ "Testing assistance" is vague
- ❌ "Software development projects" is too broad
- ❌ No specific test types mentioned (unit, integration, E2E)
- ❌ No testing frameworks mentioned (JUnit, pytest, Jest)
- ❌ No trigger phrases for common testing tasks

### Expected Trigger Rate: < 20%
```
"Write unit tests" → ❌ Won't trigger
"Test my API" → ❌ Won't trigger
"E2E testing setup" → ❌ Won't trigger
```

---

## Example 5: Release Management

```yaml
---
name: release
description: Useful for releases.
---

# Release Management

This skill helps with releasing software.
```

### Problems
- ❌ "Useful for releases" provides no information
- ❌ No action verbs
- ❌ No specific tasks (versioning, changelogs, git tagging)
- ❌ No tools mentioned (npm, maven, gradle)
- ❌ Extremely vague description

### Expected Trigger Rate: < 10%
```
"Prepare for release" → ❌ Won't trigger
"Generate changelog" → ❌ Won't trigger
"Tag release version" → ❌ Won't trigger
```

---

## Common Patterns in Bad Descriptions

1. **Vague verbs**: "helps with", "useful for", "assistance for"
2. **Broad terms**: "stuff", "projects", "applications", "management"
3. **Academic language**: "schema evolution", "data analysis helper"
4. **No triggers**: No phrases users actually say
5. **No specifics**: No tools, file types, or technologies mentioned
6. **Too short**: Under 50 characters provides no context

## Impact of Vague Descriptions

| Metric | Bad Description | Good Description |
|--------|----------------|------------------|
| Trigger rate | < 30% | > 80% |
| User satisfaction | Low (skill doesn't activate) | High (skill works when needed) |
| Development time wasted | High (debugging why skill won't trigger) | Low (works as expected) |
| Context efficiency | Poor (users give up, ask different way) | Good (activates on first try) |

## Conclusion

Vague descriptions are the #1 reason skills fail to trigger. The cost of writing a good description upfront is minimal compared to the ongoing cost of debugging poor triggering.

**See [after/specific-description.md](../after/specific-description.md) for the fixed versions.**