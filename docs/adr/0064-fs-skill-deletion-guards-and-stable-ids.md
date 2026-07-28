# ADR-0064: FS-Skill Deletion Guards and Stable IDs

**Status**: Approved

**Context**

FS is the root of the lineage chain (ADR-0054). FS requirements are referenced by SRS items, which are referenced by ADRs, and so on. Deleting or changing an FS ID breaks all downstream references.

**Decision**

FS-skill enforces two guards:

1. **Stable IDs**:
   - FS-skill already generates EARS-formatted IDs (e.g., `GRP-FS-CRUD-001`)
   - These IDs are immutable once an FS requirement is published
   - Renaming an ID is treated as deletion + re-creation, triggering cascade guards

2. **Deletion blocks on orphans** (implements ADR-0057 for FS):
   - Before allowing an FS item to be deleted, FS-skill scans all SRS documents for `**Source FS**: <ID>`
   - If any references found, block deletion
   - Surface the list of orphaned SRS items
   - Require user to re-anchor each SRS item to another FS item (or delete the SRS item)
   - Only after all re-anchored, allow FS item deletion

3. **Frontmatter**:
   ```yaml
   ---
   artifact-type: fs
   lineage-rules: root
   ---
   ```
   Signals to critic that this is the lineage root; upstream validation is skipped.

**Consequences**

- FS IDs are canonical and unchanging
- No orphaned SRS→FS references can exist in the system
- Deletion is guarded but permitted once dependents are resolved
- FS is formally recognized as the lineage root by both skill and critic
