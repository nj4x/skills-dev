---
name: YOUR-SKILL-NAME
description: [ACTION VERB] [SPECIFIC DOMAIN] using [SPECIFIC TOOLS]. Use when [TRIGGER PHRASE 1], [TRIGGER PHRASE 2], or [TRIGGER PHRASE 3].
---

# Skill Name

## Overview

[Brief 1-2 sentence description of what this skill does]

## When to Use This Skill

This skill activates when you need to:
- [Specific task 1]
- [Specific task 2]
- [Specific task 3]

## Core Concepts

### [Concept 1]
[Brief explanation with example]

### [Concept 2]
[Brief explanation with example]

## Common Workflow

### Step 1: [First Step]

[Description and concrete example]

```python
# Code example if applicable
```

### Step 2: [Second Step]

[Description and concrete example]

### Step 3: [Third Step]

[Description and concrete example]

## Examples

### Example 1: [Task Description]

**Request:** [User's request]

**Process:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Outcome:** [Result]

## Key Patterns

- ✅ **Good Pattern:** [Description with example]
- ❌ **Avoid:** [Anti-pattern description]

## Common Issues

**Issue:** [Problem description]

**Solution:**
1. [Step 1]
2. [Step 2]

## Quick Reference

| Task | Command | Notes |
|------|---------|-------|
| [Task 1] | [Command/Step] | [Notes] |
| [Task 2] | [Command/Step] | [Notes] |
| [Task 3] | [Command/Step] | [Notes] |

---

## Template Usage Instructions

### 1. Replace Placeholders

Search and replace these placeholders:

- `YOUR-SKILL-NAME` → Your skill name (kebab-case)
- `[ACTION VERB]` → Deploy, Analyze, Generate, Configure
- `[SPECIFIC DOMAIN]` → AWS using CDK, CSV files with pandas, etc.
- `[SPECIFIC TOOLS]` → CDK, pandas, JUnit, etc.
- `[TRIGGER PHRASE 1, 2, 3]` → Phrases users might say

### 2. Fill in Sections

Complete each section with specific content:
- Overview: 1-2 sentence summary
- When to Use: List 3 specific tasks
- Core Concepts: 2-3 key concepts with examples
- Common Workflow: 3-step process with examples
- Examples: 1-2 concrete examples
- Key Patterns: Good/bad practices
- Common Issues: Troubleshooting guide
- Quick Reference: Task/command table

### 3. Token Budget

Keep SKILL.md under 5,000 tokens:
- Overview: ~100 tokens
- When to Use: ~200 tokens
- Core Concepts: ~800 tokens
- Common Workflow: ~1,000 tokens
- Examples: ~1,200 tokens
- Key Patterns: ~600 tokens
- Common Issues: ~600 tokens
- Quick Reference: ~500 tokens
- **Total: ~5,000 tokens**

### 4. Testing

Test description with 5 phrasings:
1. Most direct phrasing
2. Slightly different wording
3. Synonyms
4. Short/casual
5. Unrelated edge case (should NOT trigger)

Success criteria: 4/5+ phrases trigger (≥ 80%)

### 5. Quality Check

Before publishing:
- [ ] Description is specific and actionable
- [ ] Name uses kebab-case
- [ ] SKILL.md under 5k tokens
- [ ] Concrete examples provided
- [ ] Tested with multiple phrasings
- [ ] Token budget tracked

---

## Example: Filled Template

```yaml
---
name: data-analysis
description: Analyze CSV and Excel data files using pandas. Use when exploring datasets, generating statistics, or creating visualizations from tabular data.
---

# Data Analysis

## Overview

Guide for analyzing CSV and Excel data files using pandas for exploration, cleaning, and visualization.

## When to Use This Skill

This skill activates when you need to:
- Explore and understand data structure
- Generate statistics and summaries
- Create data visualizations

## Core Concepts

### DataFrames
Pandas DataFrames are 2D labeled data structures.

```python
import pandas as pd
df = pd.read_csv("data.csv")
print(df.head())
```

### Data Cleaning
Handling missing values and duplicates.

```python
df = df.dropna()  # Remove missing values
df = df.drop_duplicates()  # Remove duplicates
```

## Common Workflow

### Step 1: Load and Explore Data

Read the file and understand its structure.

```python
import pandas as pd

df = pd.read_csv("data.csv")
print(df.info())  # Column types and non-null counts
print(df.describe())  # Statistical summary
```

### Step 2: Clean Data

Handle missing values and inconsistencies.

```python
# Remove rows with missing critical values
df = df.dropna(subset=['column_name'])

# Fill missing values with mean
df['column_name'] = df['column_name'].fillna(df['column_name'].mean())
```

### Step 3: Generate Insights

Calculate statistics and create visualizations.

```python
# Calculate statistics
mean_value = df['column_name'].mean()
print(f"Mean: {mean_value}")

# Create visualization
import matplotlib.pyplot as plt
df['column_name'].hist()
plt.show()
```

## Examples

### Example 1: Sales Data Analysis

**Request:** "Analyze the sales_data.csv file"

**Process:**
1. Load CSV with pandas
2. Check for missing values
3. Calculate total sales by category
4. Create bar chart

**Outcome:** Complete analysis with statistics and visualization

## Key Patterns

- ✅ **Good:** Always check `df.info()` first to understand data types
- ❌ **Avoid:** Don't modify the original DataFrame, work on a copy

## Common Issues

**Issue:** `pd.read_csv()` fails with encoding error

**Solution:**
1. Try `encoding='utf-8'` or `encoding='latin-1'`
2. Check file with text editor to verify encoding
3. Use `encoding_errors='ignore'` as last resort

## Quick Reference

| Task | Command | Notes |
|------|---------|-------|
| Load CSV | `df = pd.read_csv("file.csv")` | Most common format |
| Load Excel | `df = pd.read_excel("file.xlsx")` | Requires openpyxl |
| Show info | `df.info()` | Column types, non-null counts |
| Show stats | `df.describe()` | Mean, std, min, max, quartiles |
| Drop NA | `df = df.dropna()` | Removes rows with missing values |
| Fill NA | `df = df.fillna(value)` | Replaces missing values |
```

---

**For more guidance, see:**
- [SKILL.md](../SKILL.md) - Complete skill authoring guide
- [checklists/pre-publish-checklist.md](../checklists/pre-publish-checklist.md) - Quality verification
- [docs/decision-framework.md](../docs/decision-framework.md) - Tool selection guidance