# ADR-0062: Implement Skill—Verify-Then-Check Checklist Workflow

**Status**: Approved

**Context**

Implement skill finalizes tickets by updating their status to `done`. Tickets often contain checklists of acceptance criteria or implementation steps. Currently, implement does not systematically verify and mark off checklist items, leading to inconsistent record-keeping.

**Decision**

After code-review passes and all Major/Critical findings are resolved, implement follows this checklist workflow:

1. Extract the ticket's checklist (markdown `- [ ]` items)
2. For each unchecked item:
   - **Verify** the item is actually done:
     - Run relevant tests (if test IDs or names are in the item)
     - Inspect code to confirm behavior (if behavioral)
     - Check output logs or state (if observable)
   - Note the verification method (e.g., "test: SRS-GRP-FR-2.0.1-P-001 passed")
   - **Check** the item: `- [x]`
3. If an item cannot be verified (no test, no code, no observable behavior):
   - Do not check it
   - Add a comment: "Item not verifiable—requires manual review or acceptance"
4. Once all verifiable items are checked:
   - Update ticket `Status: done`
   - Update spec `Status: done` (if applicable)

**Consequences**

- Checklists become a reliable record of what was verified, not just wishes
- Non-verifiable items are flagged explicitly, not rubber-stamped
- Ticket status `done` is meaningful—all checklist items are either verified or documented as unverifiable
- Implement skill acts as a consistency gate for ticket completion
