# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a documentation-first workspace for Claude Code skills. Most top-level category directories contain independently installable skills; `mcp/` holds Python MCP packages and `hooks/` holds Claude Code hook scripts. There is no repository-wide build, lint, or test command.

## Detailed guidance

How skills are structured, installed, and grouped into categories.
@docs/agents/skill-authoring.md

Cross-skill dependency contracts to preserve when editing multi-turn skills.
@docs/agents/skill-dependencies.md

When to use `fd`/`rg` vs `mcp-vectors`, plus mandatory entity-graph pre-condition gates.
@docs/agents/search-strategy.md

The `mcp/mcp-vectors` package: layout, dev commands, and Qdrant/SQLite storage model.
@docs/agents/mcp-vectors.md

The `hooks/` say-cue system and when multi-turn skills must emit audio cues.
@docs/agents/hooks.md

How issues are tracked as markdown files under `.scratch/<feature>/`.
@docs/agents/issue-tracker.md

Domain terminology and architecture decisions for this workspace.
@docs/agents/domain.md
