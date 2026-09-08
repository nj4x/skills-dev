---
name: task-execution
description: Use when planning or executing a multi-file task, research, or autonomous loop — covers deliver-first order, fan-out to parallel sub-agents, and autonomous loop behavior.
---

## Deliver-first

Deliver plan or research text first; wait for user approval before reading files or making edits.

## Fan-out execution

Fan out any multi-file or multi-phase task into independent sub-phases, each to a separate `general-purpose` sub-agent (`subagent_type: "general-purpose"`), instructed to implement its module, write and pass its own tests, and avoid touching shared files. After all agents report back, run a reconciliation pass — check that interfaces are consistent across every module, fix any mismatches in lockstep, run the full suite, and commit only when all tests pass with zero regressions.

## Autonomous loops

When the user requests an autonomous loop (debug, fix-and-verify, requirements-to-SRS sync), proceed without pausing for manual approval and persist intermediate research/findings to disk as you go.
