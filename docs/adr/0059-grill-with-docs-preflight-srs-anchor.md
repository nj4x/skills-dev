# ADR-0059: Grill-With-Docs Pre-Flight SRS Anchor Check for ADRs

**Status**: Approved

**Context**

ADRs must trace to SRS requirements (ADR-0054). Unlike specs and tickets (which can defer to critic for lineage validation), ADRs are captured during an interactive grilling session where the user is present and context is hot.

Deferring SRS anchor resolution to critic post-hoc would leave the user unable to resolve it interactively—critic is read-only and cannot loop back to ask clarifying questions.

**Decision**

grill-with-docs performs a **pre-flight SRS anchor check** before finalizing each ADR:

1. After drafting an ADR, ask: "Which SRS requirement(s) does this ADR satisfy?"
2. User names one or more SRS IDs
3. grill-with-docs validates each ID exists in the SRS document(s)
4. If any ID is not found:
   - Offer: "Create new SRS requirement(s) now?"
   - If yes: draft the missing SRS item(s) inline, get approval, write to SRS doc
   - If no: block ADR finalization (unanchored ADR is invalid)
5. Populate `**Source SRS**:` field with all validated IDs
6. Continue to next ADR

**Consequences**

- Every ADR has a valid SRS anchor before critic sees it
- SRS document is updated during grilling as needed
- User approval is required for all new SRS items
- Critic Group F will not flag missing SRS anchors on ADRs (they are pre-validated)
- grill-with-docs must read SRS document(s) at session start to validate IDs
