# AGENTS.md

Guidance for coding agents working in this repository.

## Overview

This is a documentation-first workspace for Claude Code skills. Each skill lives in `skills/<category>/<skill>/` and installs independently; `mcp/` holds Python MCP packages and `hooks/` holds Claude Code hook scripts. There is no repository-wide build, lint, or test command.

## Detailed guidance

How skills are structured, installed, and grouped into categories.
See `docs/agents/skill-authoring.md`.

Cross-skill dependency contracts to preserve when editing multi-turn skills.
See `docs/agents/skill-dependencies.md`.

When to use `fd`/`rg` vs `mcp-vectors`, plus the `search_root` index pre-condition.
See `docs/agents/search-strategy.md`.

The `mcp/mcp-vectors` package: layout, dev commands, and Qdrant/SQLite storage model.
See `docs/agents/mcp-vectors.md`.

The `hooks/` say-cue system and when multi-turn skills must emit audio cues.
See `docs/agents/hooks.md`.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues; skills use `gh issue create` to publish. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context repo with root `GLOSSARY.md`, `docs/adr/`, and `.data/requirements/`. See `docs/agents/domain.md`.
