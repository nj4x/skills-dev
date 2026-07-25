# After: Specific Description Examples

These examples show fixed descriptions that trigger reliably. Compare with [before/vague-description.md](../before/vague-description.md).

## Example 1: AWS Deployment (FIXED)

```yaml
---
name: aws-cdk-deploy
description: Deploy applications to AWS using CDK. Use when deploying, updating infrastructure, or managing AWS resources.
---

# AWS CDK Deployment

Guide for deploying and managing AWS infrastructure using Cloud Development Kit.
```

### Improvements
- ✅ Action verb: "Deploy"
- ✅ Specific domain: "AWS using CDK"
- ✅ Trigger phrases: "deploying, updating infrastructure, or managing AWS resources"
- ✅ Specific tool: "CDK"
- ✅ Clear scope: deployment and infrastructure management

### Expected Trigger Rate: > 90%
```
"Deploy to AWS" → ✅ Triggers
"Set up infrastructure" → ✅ Triggers
"CDK deployment" → ✅ Triggers
"Update AWS resources" → ✅ Triggers
"Infrastructure as code" → ✅ Triggers
```

---

## Example 2: Data Analysis (FIXED)

```yaml
---
name: data-analysis
description: Analyze CSV and Excel data files using pandas. Use when exploring datasets, generating statistics, or creating visualizations from tabular data.
---

# Data Analysis

Work with CSV and Excel data files using pandas for exploration, cleaning, and visualization.
```

### Improvements
- ✅ Action verb: "Analyze"
- ✅ Specific file types: "CSV and Excel data files"
- ✅ Specific tool: "pandas"
- ✅ Trigger phrases: "exploring datasets, generating statistics, or creating visualizations"
- ✅ Clear use cases: data exploration, statistics, visualization

### Expected Trigger Rate: > 85%
```
"Analyze sales_data.csv" → ✅ Triggers
"Create visualizations" → ✅ Triggers
"Data cleaning" → ✅ Triggers
"Explore my dataset" → ✅ Triggers
"Generate statistics" → ✅ Triggers
```

---

## Example 3: Database Migration (FIXED)

```yaml
---
name: database-migration
description: Safely evolve database schemas. Use when adding columns, renaming tables, creating indexes, or performing migrations. Covers rollback procedures and testing strategies.
---

# Database Migration

Guide for safe database schema evolution with rollback procedures and testing strategies.
```

### Improvements
- ✅ Action verb: "Safely evolve"
- ✅ Specific domain: "database schemas"
- ✅ Trigger phrases: "adding columns, renaming tables, creating indexes, or performing migrations"
- ✅ Concrete operations users actually do
- ✅ Mentions testing and rollback (important safety features)

### Expected Trigger Rate: > 80%
```
"Add a column to users table" → ✅ Triggers
"Migrate database schema" → ✅ Triggers
"Update table structure" → ✅ Triggers
"Create index" → ✅ Triggers
"Rename table" → ✅ Triggers
```

---

## Example 4: Testing (FIXED)

```yaml
---
name: java-testing
description: Write unit and integration tests for Java applications using JUnit 5 and Mockito. Use when testing controllers, services, or repositories. Covers test setup, assertions, mocking, and test coverage.
---

# Java Testing

Comprehensive guide for testing Java applications with JUnit 5 and Mockito.
```

### Improvements
- ✅ Action verb: "Write"
- ✅ Specific language: "Java applications"
- ✅ Specific frameworks: "JUnit 5 and Mockito"
- ✅ Trigger phrases: "testing controllers, services, or repositories"
- ✅ Clear scope: unit and integration tests
- ✅ Specific test aspects: setup, assertions, mocking, coverage

### Expected Trigger Rate: > 85%
```
"Write unit tests" → ✅ Triggers
"Test my API" → ✅ Triggers
"E2E testing setup" → ❌ Won't trigger (but that's OK - E2E is different)
"Mock dependencies" → ✅ Triggers
"Test service layer" → ✅ Triggers
```

---

## Example 5: Release Management (FIXED)

```yaml
---
name: release-management
description: Generate release notes from git commits and manage version bumps. Use when preparing releases, writing changelogs, updating package.json versions, or summarizing recent changes. Covers semantic versioning and git tagging.
---

# Release Management

Automate release workflows with changelog generation and version management.
```

### Improvements
- ✅ Action verbs: "Generate", "manage"
- ✅ Specific tasks: "release notes from git commits", "version bumps"
- ✅ Trigger phrases: "preparing releases, writing changelogs, updating package.json versions"
- ✅ Concrete actions users take
- ✅ Specific tools: git, package.json
- ✅ Mentions semantic versioning

### Expected Trigger Rate: > 80%
```
"Prepare for release" → ✅ Triggers
"Generate changelog" → ✅ Triggers
"Tag release version" → ✅ Triggers
"Update version in package.json" → ✅ Triggers
"Summarize recent changes" → ✅ Triggers
```

---

## The Fix Formula

All these improved descriptions follow the same pattern:

```
[Action verb] + [Specific domain] + [Specific tools] + [Trigger phrases]
```

### Breakdown

1. **Action Verb** (What it does)
   - Deploy, Analyze, Evolve, Write, Generate
   - Start the description with what the skill actually accomplishes

2. **Specific Domain** (Where it applies)
   - AWS using CDK, CSV and Excel files, database schemas, Java applications
   - Be specific about the technology stack or domain

3. **Specific Tools** (What it uses)
   - CDK, pandas, JUnit 5, Mockito, git, package.json
   - Mention the actual tools, frameworks, or file types

4. **Trigger Phrases** (When to use it)
   - "Use when [phrase 1], [phrase 2], or [phrase 3]"
   - Include 3-5 phrases users actually say
   - Cover different ways of saying the same thing

### Example Construction

```
# Bad:
description: Data analysis helper.

# Good:
description: [Analyze] [CSV and Excel data files] [using pandas]. [Use when exploring datasets, generating statistics, or creating visualizations from tabular data].

# Structure:
[Action verb] + [Domain] + [Tools] + [Trigger phrases]
```

---

## Impact of Good Descriptions

| Metric | Bad Description | Good Description |
|--------|----------------|------------------|
| Trigger rate | < 30% | > 80% |
| User satisfaction | Low | High |
| Development time wasted | High | Low |
| Context efficiency | Poor | Good |
| Maintenance burden | High (ongoing debugging) | Low (works reliably) |

---

## Before/After Comparison: AWS Deployment

### Before (20% trigger rate)
```yaml
name: aws-helper
description: Helps with AWS stuff.
```

**Test Results:**
```
"Deploy to AWS" → ❌ Won't trigger
"Set up infrastructure" → ❌ Won't trigger
"CDK deployment" → ❌ Won't trigger
"Cloud setup" → ❌ Won't trigger
```

### After (90% trigger rate)
```yaml
name: aws-cdk-deploy
description: Deploy applications to AWS using CDK. Use when deploying, updating infrastructure, or managing AWS resources.
```

**Test Results:**
```
"Deploy to AWS" → ✅ Triggers
"Set up infrastructure" → ✅ Triggers
"CDK deployment" → ✅ Triggers
"Cloud setup" → ❌ Won't trigger (acceptable edge case)
"Infrastructure as code" → ✅ Triggers
```

**Improvement:** 350% increase in trigger rate!

---

## Key Takeaways

1. **Specificity is everything** - Vague descriptions won't trigger
2. **Include action verbs** - Start with what the skill does
3. **List trigger phrases** - Include phrases users actually say
4. **Specify tools and domains** - CDK, pandas, JUnit, not just "AWS", "data", "testing"
5. **Test with multiple phrasings** - Verify 4/5+ phrases trigger
6. **Keep under 1024 characters** - Description has a character limit

---

## Testing Your Description

After writing your description, test it with 5 phrases:

1. Most direct phrasing (should work)
2. Slightly different wording (common variant)
3. Synonyms (different vocabulary)
4. Short/casual (how people actually talk)
5. Unrelated edge case (should NOT trigger)

If 4/5+ trigger, you're good. If < 3/5, add missing trigger phrases to your description.

---

## Conclusion

Good descriptions transform skills from unreliable (triggering < 30% of the time) to reliable (triggering > 80% of the time). The effort to write a good description upfront pays dividends in reduced debugging time and better user experience.

**Compare with [before/vague-description.md](../before/vague-description.md) to see the transformation.**