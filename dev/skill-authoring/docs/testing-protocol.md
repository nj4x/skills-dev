# Skill Testing Protocol

A systematic approach to verify your skill triggers correctly and Cline follows the instructions.

## Overview

Testing is critical because you can't predict how Cline will match your description. This protocol provides a 5-step methodology to ensure reliable skill triggering and execution.

## Step 1: Description Trigger Testing

**Goal**: Verify the skill triggers when users phrase requests in different ways.

### Process

1. Write your initial description
2. Create 5 test phrases a user might say
3. Test each phrase in Cline
4. Check if the skill activates
5. Iterate until 4/5+ phrases trigger the skill

### Test Phrasing Matrix

| Test Phrase | Triggered? | Notes |
|-------------|------------|-------|
| Phrase 1 (most direct) | ✅/❌ | Expected to work |
| Phrase 2 (slightly different wording) | ✅/❌ | Common variant |
| Phrase 3 (synonyms) | ✅/❌ | Different vocabulary |
| Phrase 4 (short/casual) | ✅/❌ | How people actually talk |
| Phrase 5 (unrelated edge case) | ✅/❌ | Should NOT trigger |

### Example: AWS CDK Deploy Skill

**Initial Description:**
```yaml
description: Deploy applications to AWS using CDK.
```

**Test Results:**
| Phrase | Result | Issue |
|-------|--------|-------|
| "Help me deploy to AWS" | ✅ Triggers | Good |
| "Set up AWS infrastructure" | ❌ No trigger | Missing "infrastructure" in description |
| "CDK deployment" | ✅ Triggers | Good |
| "Cloud setup" | ❌ No trigger | Missing "cloud" synonym |
| "Infrastructure as code" | ❌ No trigger | Missing IaC terminology |

**Improved Description:**
```yaml
description: Deploy applications to AWS using CDK. Use when deploying, updating infrastructure, or managing AWS resources.
```

**Retest Results:**
| Phrase | Result | Success Rate |
|-------|--------|--------------|
| "Help me deploy to AWS" | ✅ | 100% |
| "Set up AWS infrastructure" | ✅ | 100% |
| "CDK deployment" | ✅ | 100% |
| "Cloud setup" | ❌ | 80% (acceptable) |
| "Infrastructure as code" | ✅ | 100% |

### Success Criteria

- **Excellent**: 5/5 phrases trigger (100%)
- **Good**: 4/5 phrases trigger (80%)
- **Acceptable**: 3/5 phrases trigger (60%)
- **Needs Improvement**: < 3/5 phrases trigger (< 60%)

If below acceptable, add missing trigger phrases to your description.

---

## Step 2: Instruction Following Test

**Goal**: Verify Cline follows the instructions correctly when the skill activates.

### Process

1. Activate the skill (use a phrase that reliably triggers it)
2. Give a specific task that requires following the skill's instructions
3. Check if Cline follows the exact steps from SKILL.md
4. Look for deviations or missed instructions

### Example: Data Analysis Skill

**Skill Instruction:**
```markdown
When analyzing data files, follow this workflow:

1. Read a sample of the file to understand its structure
2. Identify column types and data quality issues
3. Note any missing values or anomalies
4. Ask clarifying questions about specific insights
5. Use pandas for data manipulation
```

**Test Request:**
"Analyze the sales_data.csv file"

**Checklist:**
- [ ] Did Cline read the sample first?
- [ ] Did Cline identify column types?
- [ ] Did Cline check for missing values?
- [ ] Did Cline ask clarifying questions?
- [ ] Did Cline use pandas for manipulation?

### Common Deviations

If Cline deviates from instructions, check:

1. **Are instructions clear?** - Abstract instructions are hard to follow
   - **Fix**: Add concrete examples with code

2. **Is the order logical?** - Cline reads sequentially
   - **Fix**: Front-load critical steps, number them clearly

3. **Are examples provided?** - Examples guide implementation
   - **Fix**: Add complete code examples, not snippets

4. **Are edge cases covered?** - Cline may not know what to do
   - **Fix**: Add error handling guidance

---

## Step 3: Token Budget Verification

**Goal**: Ensure SKILL.md stays under the 5k token limit.

### Process

1. Count tokens in your SKILL.md
2. Compare to 5k limit
3. If over limit, identify sections to move to docs/

### Token Counting Methods

**Method 1: Word Count Estimation**
- Average: 1 word ≈ 1.3 tokens
- Quick check: Word count × 1.3 ≈ token count

**Method 2: Character Count**
- Average: 4 characters ≈ 1 token
- Quick check: Character count / 4 ≈ token count

**Method 3: Actual Token Count**
Use a tokenizer tool for precise count:
```python
import tiktoken
enc = tiktoken.encoding_for_model("gpt-4")
text = open("SKILL.md").read()
tokens = enc.encode(text)
print(f"Token count: {len(tokens)}")
```

### Token Budget Template

```
Token Budget Analysis for: [skill-name]

Section                              | Tokens | % of Total
-------------------------------------|--------|----------
Description field guidance          | 1200   | 40%
Common workflows                    | 600    | 20%
Scripts vs instructions             | 450    | 15%
Token management strategy           | 450    | 15%
Naming & structure                  | 300    | 10%
-------------------------------------|--------|----------
TOTAL                               | 3000   | 100%
-------------------------------------|--------|----------
REMAINING                           | 2000   | 40%
-------------------------------------|--------|----------
```

### If Over Limit

1. **Identify low-priority sections** (what can be moved to docs/)
2. **Create docs/ file** for that section
3. **Reference it** from SKILL.md: `See [advanced.md](docs/advanced.md)`
4. **Retest** to ensure supporting docs load correctly

---

## Step 4: Edge Case Testing

**Goal**: Verify skill handles unexpected situations gracefully.

### Test Cases

#### Edge Case 1: Ambiguous Request
**Request:** User request matches multiple skills

**Test:**
```
Request: "Help with data"

Available skills:
- data-analysis: "Analyze CSV and Excel data files..."
- ml-model-deployment: "Deploy machine learning models..."
```

**Expected:** Most specific skill triggers (data-analysis for file analysis)

#### Edge Case 2: Unrelated Trigger
**Request:** Phrase accidentally triggers wrong skill

**Test:**
```
Description: "Generate release notes from git commits"
Request: "I need notes for my meeting"
```

**Expected:** Should NOT trigger (too broad match)

**Fix:** Make description more specific:
```yaml
description: Generate release notes from git commits. Use when preparing releases, writing changelogs, or summarizing recent changes.
```

#### Edge Case 3: Empty/Minimal Request
**Request:** User asks generic question that skill should help with

**Test:**
```
Request: "How do I deploy?"
Skill: aws-cdk-deploy
```

**Expected:** Skill triggers and Cline asks clarifying questions

#### Edge Case 4: Context-Dependent Workflow
**Request:** Skill provides flexible instructions that should adapt

**Test:**
```
Request: "Deploy to staging"
Skill instruction: "Ask user: Which region? Which environment? Stack name?"
```

**Expected:** Cline uses "staging" from request, doesn't ask for environment again

---

## Step 5: Regression Testing

**Goal**: Ensure skill improvements don't break existing functionality.

### When to Run Regression Tests

- After modifying description
- After reorganizing SKILL.md structure
- After splitting content into docs/
- After adding new sections

### Regression Test Checklist

- [ ] Previous test phrases still trigger skill
- [ ] Instruction following still works
- [ ] Token budget still under limit
- [ ] Edge cases still handled correctly
- [ ] No new false positives (triggering when shouldn't)

### Version Tracking

Track skill versions to identify when issues were introduced:

```
skill-authoring/
├── SKILL.md
├── docs/
│   └── testing-protocol.md
└── test-results/
    ├── v1.0-test-results.md  # Initial version
    ├── v1.1-test-results.md  # After description improvement
    └── v1.2-test-results.md  # After restructuring
```

**Test Result Template:**
```markdown
# Skill Test Results - v1.1

**Skill:** aws-cdk-deploy
**Date:** 2026-03-04
**Description Changes:** Added "infrastructure" and "managing resources" to description

## Trigger Testing
| Phrase | v1.0 Result | v1.1 Result | Regression? |
|-------|-------------|-------------|-------------|
| "Help me deploy to AWS" | ✅ | ✅ | No |
| "Set up AWS infrastructure" | ❌ | ✅ | Fixed ✅ |
| "CDK deployment" | ✅ | ✅ | No |
| "Infrastructure as code" | ❌ | ✅ | Fixed ✅ |
| **Success Rate** | 60% | 100% | Improved |

## Token Budget
| Version | Tokens | Status |
|---------|--------|--------|
| v1.0 | 2800 | ✅ OK |
| v1.1 | 2950 | ✅ OK |

## Issues Found
None - improvements successful

## Next Steps
No changes needed
```

---

## Step 6: Adversarial Testing

**Goal**: Surface edge cases the author didn't consider by deliberately trying to break the skill.

### Process

1. Run the skill against real tasks to build familiarity
2. Deliberately probe four failure modes:
   - Near-miss triggers (phrases that almost match but shouldn't fire)
   - Mis-invocations (activate the skill then give it an ambiguous or incomplete request)
   - Fragile-step stress tests (send a task that exercises the skill's most brittle steps)
   - External audit ("What edge cases break this skill?" — ask a separate LLM session)
3. Patch the specific line responsible for each failure found

### Test Types

#### Near-Miss Trigger Test

**Goal:** Confirm the skill doesn't fire on related-but-wrong requests.

```
Skill: aws-cdk-deploy
Description: "Deploy applications to AWS using CDK. Use when deploying, updating infrastructure, or managing AWS resources."

Near-miss prompts (should NOT trigger):
- "What is CDK?" → ❌ Should not trigger (question, not a task)
- "Help me with Azure deployment" → ❌ Should not trigger (wrong cloud)
- "Set up my local dev environment" → ❌ Should not trigger (local, not AWS)

Expected: none of these fire the skill.
If any do: narrow the description.
```

#### Fragile-Step Test

**Goal:** Confirm the agent uses the skill's checkpoints rather than improvising.

```
Identify the most brittle step in the skill body (the one where a wrong move causes the most damage).
Give the agent a task that exercises that step.

Verify:
- Did the agent follow the checkpoint exactly?
- Did it verify state before acting?
- Did it follow the rollback path when the check failed?

If the agent improvised: add more rigid instructions to that specific step.
```

#### External Audit

**Goal:** Find gaps the author's own perspective misses.

```
In a separate session with no skill context loaded, ask:
"I have a skill for [domain]. What are the most likely edge cases or failure modes it might not handle?"

Review the named edge cases. For each one your skill doesn't address:
- If it's a common case: add handling to the body
- If it's rare: add a note in the relevant docs/ file
- If it's out of scope: add a "This skill does not handle X" boundary statement
```

### Success Criteria

- All near-miss prompts correctly don't trigger the skill
- Fragile steps are followed exactly (no improvisation)
- External audit surfaces ≤ 2 unhandled edge cases (and you've decided to handle or explicitly exclude each)

---

## Troubleshooting Common Issues

### Issue 1: Skill Won't Trigger

**Symptoms:** Test phrases don't activate the skill

**Diagnosis:**
1. Description is too vague
2. Missing trigger phrases
3. Description doesn't match how users phrase requests

**Fixes:**
1. Add action verbs: "Deploy", "Analyze", "Generate"
2. Add trigger phrases: "Use when [doing X, Y, Z]"
3. Include specific tools, file types, or technologies
4. Test with 5 phrases, iterate until 4/5+ work

### Issue 2: Skill Triggers But Instructions Aren't Followed

**Symptoms:** Skill activates but Cline doesn't follow SKILL.md

**Diagnosis:**
1. Instructions are too abstract
2. Missing concrete examples
3. Steps aren't clearly numbered
4. Critical info not front-loaded

**Fixes:**
1. Add complete code examples
2. Number steps clearly (1, 2, 3...)
3. Front-load critical information
4. Show expected output
5. Demonstrate error handling

### Issue 3: Skill Triggers For Unrelated Requests

**Symptoms:** Skill activates when it shouldn't

**Diagnosis:**
1. Description is too broad
2. Covers multiple domains
3. Overlapping with other skills

**Fixes:**
1. Make description more specific
2. Narrow the domain
3. Add negative constraints: "NOT for general cloud management"
4. Split into multiple focused skills

### Issue 4: SKILL.md Exceeds 5k Tokens

**Symptoms:** Slow loading, poor performance

**Diagnosis:**
1. Too much content in one file
2. Advanced topics mixed with core concepts

**Fixes:**
1. Front-load critical info (40% to description, 60% to workflows)
2. Move advanced topics to docs/
3. Reference supporting docs from SKILL.md
4. Use progressive loading

### Issue 5: Cline Ignores Supporting Docs

**Symptoms:** Referenced docs/ files don't load

**Diagnosis:**
1. Reference path is incorrect
2. Reference isn't clear
3. SKILL.md doesn't tell Cline to read the doc

**Fixes:**
1. Use explicit references: `See [advanced.md](docs/advanced.md)`
2. Add instruction: "For advanced configuration, see docs/advanced.md"
3. Test that docs load when referenced

---

## Test Automation Script

For frequent skill updates, automate testing with this script:

```bash
#!/bin/bash
# test-skill.sh - Automated skill testing

SKILL_DIR="$1"
SKILL_NAME=$(basename "$SKILL_DIR")

echo "Testing skill: $SKILL_NAME"
echo "================================"

# Step 1: Check naming convention
if [[ ! "$SKILL_NAME" =~ ^[a-z0-9-]+$ ]]; then
    echo "❌ Naming convention error: Use kebab-case"
    exit 1
fi

# Step 2: Check SKILL.md exists
if [[ ! -f "$SKILL_DIR/SKILL.md" ]]; then
    echo "❌ SKILL.md not found"
    exit 1
fi

# Step 3: Extract description
DESCRIPTION=$(grep -A 1 "^description:" "$SKILL_DIR/SKILL.md" | tail -1 | xargs)

# Step 4: Check description length
DESC_LEN=${#DESCRIPTION}
if [[ $DESC_LEN -gt 1024 ]]; then
    echo "⚠️  Warning: Description over 1024 characters ($DESC_LEN)"
fi

# Step 5: Estimate token count
TOKEN_ESTIMATE=$(wc -w "$SKILL_DIR/SKILL.md" | awk '{print int($1 * 1.3)}')
if [[ $TOKEN_ESTIMATE -gt 5000 ]]; then
    echo "❌ Token limit exceeded: ~$TOKEN_ESTIMATE tokens"
    exit 1
fi

echo "✅ All checks passed"
echo "   Description: $DESCRIPTION"
echo "   Estimated tokens: ~$TOKEN_ESTIMATE"
```

**Usage:**
```bash
chmod +x test-skill.sh
./test-skill.sh .cline/skills/aws-cdk-deploy
```

---

## Summary

Testing is not optional - it's essential for reliable skills. Follow this 5-step protocol:

1. **Description Trigger Testing** - Verify skill activates with 4/5+ phrases
2. **Instruction Following Test** - Ensure Cline follows SKILL.md correctly
3. **Token Budget Verification** - Stay under 5k tokens
4. **Edge Case Testing** - Handle unexpected situations gracefully
5. **Regression Testing** - Ensure improvements don't break existing functionality
6. **Adversarial Testing** — Near-miss triggers, fragile-step stress tests, external LLM audit

Invest time in testing upfront, and your skills will be reliable, efficient, and well-maintained.