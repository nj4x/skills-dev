# ADR-0055: Lineage Enforcement—Split Between Skill Live Validation and Critic Post-Hoc Audit

**Status**: Approved

**Context**

Lineage violations can be caught at two points: during artifact authoring (when context is hot and the user can resolve immediately) or during critic review (post-hoc, read-only). Each has different UX and safety tradeoffs.

**Decision**

Lineage enforcement is split:

1. **Skills enforce live** (fail-fast during authoring):
   - SRS-skill validates FS anchors before finalizing; drafts missing FS items inline
   - grill-with-docs validates SRS anchors before finalizing ADRs; drafts missing SRS items inline
   - code-review reports code-to-spec misalignment and broken spec-to-ADR chains as findings
   - Implement verifies and checks off ticket checklists after code-review passes

2. **Critic enforces post-hoc** (read-only audit via Group F):
   - Critic Group F validates all `Source X:` fields point to valid artifacts
   - Flags missing or dangling references as Critical (broken links) or Major (missing anchors)
   - Runs on all artifact types (SRS, ADR, spec, tickets, companions)
   - Uses convention-based lookup (no explicit paths in frontmatter)

**Failure Policy for Manually-Authored Artifacts**

Artifacts created outside skill workflows (hand-edited files, external tools, migrations) bypass live validation. This is explicitly in scope for the lineage system:

- **Discovery**: Critic Group F is the primary detection mechanism for manually-authored artifacts. It runs on all artifacts with `lineage-rules` frontmatter regardless of how the file was created.
- **Missing frontmatter**: If an artifact lacks `lineage-rules` frontmatter entirely, it is invisible to Group F (see ADR-0060 for the explicit policy on this case). The authoring user is responsible for adding frontmatter when creating artifacts outside skill workflows; skill documentation must state this requirement.
- **No retroactive blocking**: Manual artifacts that already exist with broken lineage are not retroactively blocked. They surface as Group F findings (Major or Critical per ADR-0060) and must be resolved before the next critic approval cycle.
- **Exemption path**: Users may explicitly declare an artifact as `lineage-rules: exempt` in frontmatter to suppress Group F auditing for that artifact. This decision must be documented in the artifact's own body and is flagged as an Informational finding by the critic.

**Consequences**

- Skills block completion if upstream anchors are missing but can be resolved inline
- Critic catches schema-level gaps and inconsistencies the skills may have missed
- User is never left in a broken state if they follow skill prompts
- Critic approval is not guaranteed if lineage gaps exist—user must iterate with skills
- Critic feedback on lineage is advisory; user decides whether to fix or override
- Manually-authored artifacts are in scope but detected post-hoc via critic, not live
