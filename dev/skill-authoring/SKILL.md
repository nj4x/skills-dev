---
name: skill-authoring
description: Create a new skill — Pattern A/B decision, draft, invocation mode, quality check, and publish.
disable-model-invocation: true
---

## 1. Name the bottleneck

Ask: why does the agent fail at this task today?

- "Can't do X" → **Pattern A** (capability primitive — thin script wrapper)
- "Does X badly or inconsistently" → **Pattern B** (process primitive — methodology)

For worked examples and the full decision tree, see [design-philosophy.md](docs/design-philosophy.md).

## 2. Choose invocation mode

Decide before drafting — it shapes the description you write.

- **Model-invoked**: agent fires autonomously; other skills can reach it. Pays context load. Omit `disable-model-invocation`.
- **User-invoked**: you type `/skill-name`; no autonomous reach. Zero context load. Set `disable-model-invocation: true`.

See [`SKILL-MECHANICS.md`](../writing-for-agents/SKILL-MECHANICS.md) for the full tradeoff, splitting by invocation, and router skills.

## 3. Draft SKILL.md

Write description and body against the `writing-for-agents` vocabulary: context pointers, the two loads, information hierarchy, progressive disclosure, steps and completion criteria, leading words, pruning.

Place supporting reference under `docs/` and link it with a context pointer.

## 4. Test triggering (model-invoked only)

Try 3–5 distinct phrasings of the intended request and verify the skill fires.

## 5. Publish

Symlink the skill directory into `~/.claude/skills/<name>`:

```sh
ln -s "$(pwd)/<category>/<skill>" ~/.claude/skills/<name>
```

Edits take effect immediately — no build step. Register the skill in `README.md` under its category.
