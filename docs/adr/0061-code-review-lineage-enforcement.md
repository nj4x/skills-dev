# ADR-0061: Code-Review Lineage Enforcement—Code-to-Spec Alignment and Spec-Chain Visibility

**Status**: Approved

**Context**

Code-review audits implementation against specs and architecture decisions. To close the lineage loop, code-review should report when:
1. Code implements undocumented behavior (not in the spec)
2. Code omits specified behavior (not implemented)
3. The spec itself has broken lineage (missing ADR anchor)

**Decision**

code-review adds two lineage enforcement points:

1. **Primary: Code-to-spec alignment** (critical finding grade impact):
   - Extract the spec from spec slug or ADR reference in the ticket
   - Compare code changes against spec acceptance criteria
   - Flag code that adds undocumented behavior: **Major** (undocumented scope creep)
   - Flag code that omits specified behavior: **Major** (incomplete implementation)

2. **Secondary: Spec-to-ADR chain visibility** (Minor, informational):
   - Check the spec's `**Source ADR**:` field
   - If missing or dangling, report as **Minor**: "Spec lacks valid ADR anchor; ask architect to trace this spec to its source decisions"
   - Does not impact grade; purely informational

**Consequences**

- Implementation scope is kept in sync with specification
- Spec lineage gaps are surfaced early during code review
- Code-review stays focused on code correctness; lineage repair is user's decision
- Specs with broken lineage can still be implemented (critic will catch the gap later)
