# ADR-0058: SRS-Skill Inline FS Authoring for Missing Anchors

**Status**: Approved

**Context**

When SRS-skill encounters an SRS requirement with no matching FS item, the user must either cite an existing FS requirement or create a new one. Forcing the user to context-switch to FS-skill breaks authoring flow.

**Decision**

SRS-skill handles missing FS anchors inline:

1. During SRS generation, if a requirement has no `**Source FS**:` field, SRS-skill asks: "Which FS requirement does this SRS item trace to?"
2. If user names an existing FS ID, SRS-skill validates it exists; if not found, flag error
3. If no matching FS item exists, offer: "Create new FS requirement now?"
   - If yes: draft the FS requirement in EARS format
   - Get user approval on the draft
   - Write to FS document
   - Return to SRS authoring with `**Source FS**:` populated
   - Continue
4. If user declines, SRS-skill cannot finalize (unanchored SRS is invalid)

**Consequences**

- SRS authoring is uninterrupted; missing FS items are resolved in-context
- FS document is updated as a side effect of SRS authoring
- User approval is required for all new FS items
- No orphaned SRS requirements can be finalized
