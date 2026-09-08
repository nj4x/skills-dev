# Event Types Guide

This document provides rules and patterns for identifying and documenting event types from Feature Set (FS) requirements when creating SRS documents.

## What is an Event?

An **event** is a significant occurrence in the system that:
- Represents a state change or action completion
- May trigger subsequent processing
- Can be published to or consumed from external systems
- Carries relevant data (attributes) about what happened

## Event Classification

### By Direction

| Type | Description | Flow |
|------|-------------|------|
| **Produced** | Events this system publishes | System → External |
| **Consumed** | Events this system receives | External → System |
| **Internal** | Events within the system | Component → Component |

### By Purpose

| Type | Description | Example |
|------|-------------|---------|
| **Domain Events** | Business state changes | RoleCreated, MemberAdded |
| **Integration Events** | Cross-system communication | UserSynced, OrganizationUpdated |
| **Notification Events** | Alert other systems | ValidationFailed, LimitExceeded |
| **Audit Events** | Record actions for compliance | AccessGranted, ConfigChanged |

---

## Event Identification Patterns

### Pattern 1: Event-Driven EARS Requirements

EARS "Event-driven" pattern requirements often indicate events:

```
"When [trigger], the system shall [action]"
```

**Extract both:**
- The trigger → potential **consumed event** or **internal trigger**
- The action completion → potential **produced event**

**Examples:**
```
"When a user is added to a group with assigned Admin Roles, the system shall automatically grant those role permissions to the user"
```
- Consumed/Trigger: `UserAddedToGroup`
- Produced: `PermissionsGranted`

```
"When a parent group is deleted, the system shall remove the group membership association"
```
- Trigger: `GroupDeleted`
- Produced: `MembershipRemoved`

### Pattern 2: State Change Completions

Look for phrases indicating completed actions:

| FS Pattern | Produced Event |
|------------|----------------|
| "The system shall create [X]" | `[X]Created` |
| "The system shall delete [X]" | `[X]Deleted` |
| "The system shall update [X]" | `[X]Updated` |
| "The system shall add [X] to [Y]" | `[X]AddedTo[Y]` |
| "The system shall remove [X] from [Y]" | `[X]RemovedFrom[Y]` |
| "The system shall grant [permission]" | `PermissionGranted` |
| "The system shall revoke [permission]" | `PermissionRevoked` |

### Pattern 3: External State Changes

Requirements that react to an external state change may imply event semantics:

```
"When the external assignment changes, the system shall..."
```

Determine whether the contract requires a consumed event or a produced event. Transport and invocation remain ADR decisions.

**Example:**
```
"When a role is no longer assigned, the system shall permit deletion"
```
- The requirement is a lifecycle constraint, not an invocation mechanism
- A `RoleDeleted` event may express completion when the governing contract requires it

### Pattern 4: Cascading Effects

Requirements describing cascading or propagated effects:

```
"When [X] is [action], the system shall [cascade action] to all [related Y]"
```

**Example:**
```
"When an Admin Role is removed from a group, the system shall revoke that role's permissions from all group members"
```
- Event: `AdminRoleRemovedFromGroup`
- Cascading events: Multiple `PermissionRevoked` events

---

## Event Attribute Extraction

### Core Attributes (All Events)

Every event should have:

| Attribute | Type | Description |
|-----------|------|-------------|
| `eventId` | UUID | Unique identifier for the event instance |
| `eventType` | String | Name of the event (e.g., "RoleCreated") |
| `timestamp` | DateTime | When the event occurred |
| `correlationId` | UUID | Links related events across systems |
| `sourceSystem` | String | System that produced the event |

### Domain-Specific Attributes

Extract from requirement context:

| FS Context | Event Attribute |
|------------|-----------------|
| Entity identifier mentioned | `entityId` (e.g., `roleId`, `groupId`) |
| Actor performing action | `actorId`, `actorType` |
| Before/after states | `previousValue`, `newValue` |
| Scope information | `organizationId`, `tenantId` |

**Example Extraction:**
```
FS: "When a group is created, the system shall record the Group Name, Group ID, Description, and Admin Role assignment"
```

Event: `GroupCreated`
Attributes:
- `groupId` - The created group's ID
- `groupName` - Name of the group
- `description` - Group description (optional)
- `adminRoleId` - Assigned admin role (optional)
- `createdBy` - Actor who created the group
- `organizationId` - Owning organization

---

## Event Documentation Template

### Events Produced Table

```markdown
## Events Produced

| Event Name | Trigger | Key Attributes | Source FS |
|------------|---------|----------------|-----------|
| [EventName] | [When triggered] | [Main attributes] | [FS-ID] |
```

### Events Consumed Table

```markdown
## Events Consumed

| Event Name | Source System | Handler Action | Source FS |
|------------|---------------|----------------|-----------|
| [EventName] | [Origin] | [What system does] | [FS-ID] |
```

### Detailed Event Specification

```markdown
### Event: [EventName]

**Type**: Produced | Consumed | Internal
**Trigger**: [What causes this event]
**Source FS**: [FS requirement IDs]

#### Attributes

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| eventId | UUID | Yes | Unique event identifier |
| [attr1] | [type] | Yes/No | [Description] |
| [attr2] | [type] | Yes/No | [Description] |

#### Example Payload

```json
{
  "eventId": "550e8400-e29b-41d4-a716-446655440000",
  "eventType": "[EventName]",
  "timestamp": "2024-01-15T10:30:00Z",
  "[attr1]": "[value]",
  "[attr2]": "[value]"
}
```

#### Consumers/Handlers
- [System/Component 1]: [What it does with this event]
- [System/Component 2]: [What it does with this event]
```

---

## Common Event Patterns

### CRUD Events

For each entity with CRUD operations:

| Operation | Event Name Pattern | Attributes |
|-----------|-------------------|------------|
| Create | `[Entity]Created` | All entity attributes, createdBy |
| Update | `[Entity]Updated` | entityId, changedFields, updatedBy |
| Delete | `[Entity]Deleted` | entityId, deletedBy |

### Relationship Events

For entity relationships:

| Operation | Event Name Pattern | Attributes |
|-----------|-------------------|------------|
| Add to | `[Entity]AddedTo[Parent]` | entityId, parentId, role (if applicable) |
| Remove from | `[Entity]RemovedFrom[Parent]` | entityId, parentId, reason (optional) |

### Permission Events

| Operation | Event Name Pattern | Attributes |
|-----------|-------------------|------------|
| Grant | `PermissionGranted` | permissionId, subjectId, subjectType, grantedBy |
| Revoke | `PermissionRevoked` | permissionId, subjectId, subjectType, revokedBy |

### Lifecycle Events

| State Change | Event Name Pattern | Attributes |
|--------------|-------------------|------------|
| Activate | `[Entity]Activated` | entityId, activatedBy |
| Deactivate | `[Entity]Deactivated` | entityId, deactivatedBy |
| Expire | `[Entity]Expired` | entityId, expirationReason |

---

## Event Naming Conventions

### General Rules

1. **Use past tense** - Events describe what happened
   - ✅ `RoleCreated`, `MemberAdded`
   - ❌ `CreateRole`, `AddMember`

2. **Be specific** - Include entity type in name
   - ✅ `SystemRoleCreated`, `CustomRoleCreated`
   - ❌ `RoleCreated` (if ambiguous)

3. **Use PascalCase** - Standard naming convention
   - ✅ `GroupMemberAdded`
   - ❌ `group_member_added`, `groupMemberAdded`

### Naming Patterns

| Pattern | Example |
|---------|---------|
| `[Entity]Created` | `RoleCreated` |
| `[Entity]Updated` | `RoleUpdated` |
| `[Entity]Deleted` | `RoleDeleted` |
| `[Entity][Action]ed` | `RoleAssigned`, `RoleRevoked` |
| `[Entity]AddedTo[Parent]` | `UserAddedToGroup` |
| `[Entity]RemovedFrom[Parent]` | `UserRemovedFromGroup` |
| `[Action]Completed` | `SyncCompleted`, `MigrationCompleted` |
| `[Action]Failed` | `ValidationFailed`, `SyncFailed` |

---

## Event Flow Diagrams

### Simple Event Flow

```
[Actor] → [System] → [Event] → [Consumer(s)]

Example:
Admin → RoleService → RoleCreated → AuditService, NotificationService
```

### Cascading Events

```
[Trigger Event] → [System] → [Multiple Events]

Example:
GroupDeleted → MembershipService → [MembershipRemoved] × N members
```

### Event Choreography

```
[Event A] → [System B] → [Event B] → [System C] → [Event C]

Example:
AdminRoleAssignedToGroup → PermissionService → PermissionsGranted → AuditService
```

---

## Integration Considerations

### Event Delivery

| Aspect | Consideration |
|--------|---------------|
| **Ordering** | Events may need sequential processing |
| **Idempotency** | Consumers must handle duplicate events |
| **Retry** | Failed event processing needs retry logic |
| **Dead Letter** | Unprocessable events need handling |

### Event Schema Evolution

- Events should be backward compatible
- Add new optional fields, don't remove existing fields
- Version events if breaking changes required

---

## Extraction Checklist

When analyzing FS requirements for events:

- [ ] What EARS "Event-driven" requirements exist?
- [ ] What state changes occur (create, update, delete)?
- [ ] What cascading effects are mentioned?
- [ ] What external systems are called?
- [ ] What triggers are mentioned ("When...", "Upon...", "After...")?
- [ ] What notifications or alerts are required?
- [ ] What audit requirements exist?

---

## Kafka Topic Association

Every event documented in an SRS **must** be associated with a specific Kafka topic. This enables traceability from requirements to runtime infrastructure.

### Topic Naming Convention

Kafka topics follow the pattern: `event.{domain}.{entity}`

| Segment | Description | Examples |
|---------|-------------|----------|
| `event` | Fixed prefix for all domain events | — |
| `{domain}` | The owning service/domain | `group`, `identity`, `organization`, `role` |
| `{entity}` | The primary entity affected | `group`, `member`, `user`, `assignment` |

**Examples:**
- `event.group.group` — Group lifecycle events (created, updated, deleted)
- `event.group.membership` — Membership events (added, removed, role changed, bulk)
- `event.identity.user` — User lifecycle events (deleted, updated)
- `event.organization.organization` — Organization lifecycle events
- `event.role.assignment` — Role assignment/removal events

### Event Reference Tables — Required Format

The **Events Produced** and **Events Consumed** tables in the SRS must include a `Kafka Topic` column:

```markdown
### Events Produced

| Event Name | Kafka Topic | Trigger | Key Attributes | Source FS |
|------------|-------------|---------|----------------|-----------|
| `EntityCreated` | `event.domain.entity` | Entity created | ... | FS-ID |

### Events Consumed

| Event Name | Kafka Topic | Source System | Handler Action | Source FS |
|------------|-------------|--------------|----------------|-----------|
| `ExternalEvent` | `event.ext-domain.entity` | External Service | Handler description | FS-ID |
```

### PlantUML Diagrams — Kafka Participant

In sequence diagrams, use `Kafka` as the participant name (not "Event Bus" or "Message Queue"):

```plantuml
participant "Kafka" as Kafka

Service -> Kafka: publish(EntityCreated)
note right of Kafka
topic: event.domain.entity
Consumed by:
- Consumer Service A
- Consumer Service B
end note
```

For consumed events, show Kafka as the source:

```plantuml
Kafka -> Service: consume(ExternalEvent)
note left of Kafka
topic: event.ext-domain.entity
end note
```

---

## Anti-Patterns: Not Events

These should NOT be modeled as events:

| Pattern | Reason | Better Approach |
|---------|--------|-----------------|
| UI updates | Front-end only | WebSocket/Push notification |
| Synchronous calls | Not asynchronous | API call |
| Query results | Read operation | API response |
| Scheduled jobs | Time-based, not event-based | Cron/Scheduler |
| Validation results | Synchronous check | API response with errors |