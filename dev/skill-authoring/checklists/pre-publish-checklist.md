# Pre-Publish Checklist

Use this checklist before committing or publishing a new skill. Ensure all items pass.

---

## 1. Description Quality

- [ ] Description is specific and actionable (not vague like "helps with X")
- [ ] Description includes action verbs (Deploy, Analyze, Generate, Configure)
- [ ] Description specifies domain and tools (AWS using CDK, CSV files with pandas)
- [ ] Description includes trigger phrases users might say ("Use when deploying, updating infrastructure...")
- [ ] Description is under 1024 characters
- [ ] Description tested with 3-5 phrasings (4/5+ should trigger)

---

## 2. Naming and Structure

- [ ] Skill name uses kebab-case (lowercase with hyphens)
- [ ] Skill name matches directory name exactly
- [ ] Skill name is descriptive about what it does
- [ ] SKILL.md file exists in the skill directory
- [ ] Directory structure is appropriate for complexity level:
  - Simple skills: Just SKILL.md
  - Moderate skills: SKILL.md + 1-2 docs/
  - Complex skills: Full structure (docs/, examples/, checklists/, templates/)
- [ ] If the skill should never auto-invoke (destructive ops, expensive workflows, manual-only utilities), add `disable-model-invocation: true` to frontmatter — keep the description terse since some clients still load it for discovery

---

## 3. Token Budget

- [ ] SKILL.md is under 5,000 tokens
- [ ] Token budget tracked and documented
- [ ] Large content split into docs/ files
- [ ] Supporting docs referenced from SKILL.md
- [ ] Progressive loading strategy implemented

**Token Budget Template:**
```
Section                              | Tokens | % of Total
-------------------------------------|--------|----------
Description field guidance          | 1200   | 40%
Common workflows                    | 600    | 20%
Scripts vs instructions             | 450    | 15%
Token management strategy           | 450    | 15%
Naming & structure                  | 300    | 10%
-------------------------------------|--------|----------
TOTAL                               | 3000   | 100%
```

---

## 4. Content Quality

- [ ] Critical information is front-loaded (description, naming, core concepts)
- [ ] Section headers are clear and scannable (## Error Handling, ## Configuration)
- [ ] Concrete examples are provided (not just abstract concepts)
- [ ] Code examples are complete and runnable
- [ ] Error handling is documented
- [ ] Edge cases are covered

---

## 5. Scripts vs Instructions

- [ ] Scripts used for: validation, deterministic operations, calculations
- [ ] Instructions used for: flexible workflows, decision-making, context-adaptive processes
- [ ] Scripts are token-efficient (only output enters context)
- [ ] Instructions provide enough guidance for Cline to implement

---

## 6. Trigger Testing

- [ ] Tested description with 5 different phrasings:
  - [ ] Phrase 1 (most direct): ✅ Triggers
  - [ ] Phrase 2 (slightly different wording): ✅ Triggers
  - [ ] Phrase 3 (synonyms): ✅ Triggers
  - [ ] Phrase 4 (short/casual): ✅ Triggers
  - [ ] Phrase 5 (unrelated edge case): ❌ Should NOT trigger
- [ ] Success rate is ≥ 80% (4/5+ phrases trigger)
- [ ] Missing trigger phrases added to description
- [ ] Trigger testing results documented

---

## 7. Instruction Following

- [ ] Skill activates when triggered
- [ ] Cline follows SKILL.md instructions correctly
- [ ] Steps are numbered and sequential
- [ ] Examples are referenced in instructions
- [ ] Cline can implement from the guidance provided

---

## 8. Supporting Files

If using docs/, examples/, checklists/, templates/:

- [ ] docs/ files are referenced from SKILL.md
- [ ] docs/ load only when referenced (progressive loading)
- [ ] examples/ provide complete, runnable code
- [ ] checklists/ have actionable verification steps
- [ ] templates/ provide boilerplate to accelerate development
- [ ] File paths in references are correct

---

## 9. Anti-Patterns Check

Verify your skill avoids these common mistakes:

- [ ] ❌ Vague description ("helps with X") → ✅ Specific description
- [ ] ❌ Overly broad description → ✅ Focused scope
- [ ] ❌ SKILL.md over 5k tokens → ✅ Under limit
- [ ] ❌ Abstract concepts only → ✅ Concrete examples included
- [ ] ❌ Wrong file naming (PascalCase, underscores) → ✅ kebab-case
- [ ] ❌ Missing trigger phrases → ✅ Trigger phrases included
- [ ] ❌ Not testing description → ✅ Tested with 5 phrasings
- [ ] ❌ Scripts for flexible workflows → ✅ Instructions for flexible workflows
- [ ] ❌ Over-engineered structure → ✅ Appropriate complexity
- [ ] ❌ Ignoring token budget → ✅ Tokens tracked and optimized
- [ ] ❌ Description summarizes mechanism/implementation → ✅ Description contains trigger conditions only
- [ ] ❌ Reference chains deeper than one level → ✅ All docs/ references reachable in one hop from SKILL.md
- [ ] ❌ Skill body re-teaches model training knowledge → ✅ Body contains only institutional/domain knowledge
- [ ] ❌ Third-party skills installed without audit → ✅ Audited per third-party-security.md before installation

---

## 10. Documentation

- [ ] SKILL.md is self-documenting (clear headings, logical flow)
- [ ] Supporting files have clear purposes
- [ ] References between files are accurate
- [ ] Examples explain what they demonstrate
- [ ] Checklists explain what they verify

---

## 11. Testing Verification

- [ ] Skill triggers reliably (≥ 80% success rate)
- [ ] Instructions are followed correctly
- [ ] Token budget is verified (< 5k for SKILL.md)
- [ ] Edge cases are tested and handled
- [ ] Regression testing shows no issues

---

## 12. Right Tool Choice

- [ ] Skill is appropriate (not Rule or Workflow)
- [ ] See [decision-framework.md](../docs/decision-framework.md) for guidance:
  - Always-on standards → Use Rule instead
  - Repetitive automation → Use Workflow instead
  - Domain expertise → Skill is correct ✅
  - External tools/APIs → Use MCP Server instead

---

## Final Sign-Off

Before committing or publishing:

- [ ] All 12 checklist sections passed
- [ ] Peer review completed (if applicable)
- [ ] Testing documented
- [ ] Version number updated (if updating existing skill)

---

## Scoring Rubric

Passing Score: **100%** (all items checked)

| Score | Status | Action |
|-------|--------|--------|
| 100% | ✅ Excellent | Ready to publish |
| 90-99% | ✅ Good | Minor issues acceptable, address soon |
| 80-89% | ⚠️ Needs Improvement | Fix blocking issues before publishing |
| < 80% | ❌ Not Ready | Major issues, requires significant work |

---

## Common Blocking Issues

These items MUST pass before publishing:

1. **Vague description** - Fix by following specific description formula
2. **SKILL.md over 5k tokens** - Split content into docs/ files
3. **Poor trigger rate (< 60%)** - Add missing trigger phrases
4. **Wrong naming convention** - Use kebab-case, match directory name
5. **No concrete examples** - Add complete, runnable code examples
6. **Wrong tool choice** - Verify Skill is appropriate (vs Rule or Workflow)

---

## Example: Completed Checklist

```
## 1. Description Quality
- [x] Description is specific and actionable
- [x] Description includes action verbs
- [x] Description specifies domain and tools
- [x] Description includes trigger phrases
- [x] Description is under 1024 characters
- [x] Description tested with 5 phrasings (4/5 trigger)

## 2. Naming and Structure
- [x] Skill name uses kebab-case
- [x] Skill name matches directory name
- [x] Skill name is descriptive
- [x] SKILL.md exists
- [x] Directory structure appropriate

[... all sections completed]

Final Score: 100% ✅
Status: Ready to publish
```

---

## Notes

Add any notes or observations during review:

```
Skill: aws-cdk-deploy
Reviewer: [Your Name]
Date: 2026-03-04
Notes:
- Description triggers 5/5 test phrases - excellent
- SKILL.md at 2,950 tokens - well under limit
- Examples are complete and runnable
- Ready for production use
```

---

**For more guidance, see:**
- [SKILL.md](../SKILL.md) - Main skill authoring guide
- [docs/decision-framework.md](../docs/decision-framework.md) - Skill vs Rule vs Workflow
- [docs/common-anti-patterns.md](../docs/common-anti-patterns.md) - Mistakes to avoid
- [docs/testing-protocol.md](../docs/testing-protocol.md) - Testing methodology