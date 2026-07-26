# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a documentation-first workspace for Claude Code skills. Most top-level category directories contain independently installable skills; `mcp/` holds Python MCP packages and `hooks/` holds Claude Code hook scripts. There is no repository-wide build, lint, or test command.

## Detailed guidance

How skills are structured, installed, and grouped into categories.
See `docs/agents/skill-authoring.md`.

Cross-skill dependency contracts to preserve when editing multi-turn skills.
See `docs/agents/skill-dependencies.md`.

When to use `fd`/`rg` vs `mcp-vectors`, plus mandatory entity-graph pre-condition gates.
See `docs/agents/search-strategy.md`.

The `mcp/mcp-vectors` package: layout, dev commands, and Qdrant/SQLite storage model.
See `docs/agents/mcp-vectors.md`.

The `hooks/` say-cue system and when multi-turn skills must emit audio cues.
See `docs/agents/hooks.md`.

How issues are tracked as markdown files under `.scratch/<feature>/`.
See `docs/agents/issue-tracker.md`.

Domain terminology and architecture decisions for this workspace.
See `docs/agents/domain.md`.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues; skills use `gh issue create` to publish. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context repo with root `CONTEXT.md`, `docs/adr/`, and `.data/requirements/`. See `docs/agents/domain.md`.

## Pre-conditions

Entity-graph tools require the codebase to be indexed first (`index_codebase`).

- `get_entity_callers` — Before changing a function or class signature, always call this first to identify impacted call sites. Not for discovering what a symbol does — use `get_entity_neighbors` or `search_code` instead.
- `get_entity_neighbors` — Before answering "how does X relate to Y" or tracing a dependency chain, call this (depth 2) before reading files. Not for finding a symbol by approximate name — use `search_entities` first, then `get_entity_neighbors`.
- `search_entities` — Before calling `get_entity_callers` or `get_entity_neighbors`, always call this to confirm the exact entity name. Not for conceptual or semantic retrieval — use `search_code` for that.
- `search_global` — Before making architecture-level claims about repository organization, always call this first. Not for locating a specific symbol or file — use `search_entities` or `search_code` instead.
