# Edge Cases

## Limitations

- Works best in projects with **clear milestone markers** (docs, commits, tags)
- Requires **readable git history** (meaningful commit messages)
- Assumes **staged workflow** (research → design → spec → implementation, or similar)
- Doesn't discover state from external systems (Jira, GitHub Issues, Figma, etc.) — only local artifacts
- May misclassify stage if commit messages are vague or artifacts are out of sync with reality

## Troubleshooting

**"I see the status but I'm not sure which option to pick"**
→ The skill should offer a "Discuss priorities" fallback option so you can talk through tradeoffs before committing.

**"The skill thinks we're at stage X, but we're really at stage Y"**
→ Check git history and artifact dates. Likely cause: uncommitted draft work or stale docs. Resolve the discrepancy, then re-run `/continue`.

**"I want to skip a stage or go backward"**
→ The skill offers options but doesn't force a direction. Pick an option that works for your goals, or choose "Discuss" to talk through an alternative.
