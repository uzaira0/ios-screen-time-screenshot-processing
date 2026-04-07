# Multi-Agent Consensus Analysis: Tag Ontology for Bulk-Processing Human-Verification Systems

## Executive Summary

This document presents the results of a 5-agent consensus process analyzing a proposed tag ontology for workflow state management in human-in-the-loop data processing pipelines. Each agent analyzed the system from their specialized perspective, identifying strengths, issues, and proposing amendments. The final synthesis incorporates all accepted changes into a complete, implementable ontology.

---

# Agent 1: Domain Modeler Report

## Analysis Summary

From an ontological perspective, the proposed taxonomy demonstrates strong categorical structure with clear semantic boundaries. The six-category system (ORIGIN, PROCESSING, VERIFICATION, RESOLUTION, DISPUTE, QUEUE) represents conceptually distinct dimensions of workflow state. However, several issues compromise the purity of this categorization.

The most significant conceptual issue is the conflation of different abstraction levels within categories. For example, PROCESSING mixes temporal aspects (attempted/not_attempted), outcome states (succeeded/failed), and quality metrics (confidence levels). Similarly, VERIFICATION conflates assignment lifecycle (unassigned→assigned→claimed) with verification actions (reviewed/edited/approved). This mixing creates ambiguity about what each category fundamentally represents.

Additionally, there's inconsistency in how "pending" states are handled. Some categories have explicit pending states (`resolution:pending`) while others use negative formulations (`processing:not_attempted`). The namespace scheme `category:value` is sound, but the linguistic patterns within categories vary between past participles (succeeded, failed), nouns (consensus, quorum), and adjectives (partial, unanimous), which reduces semantic consistency.

## Strengths Identified

- Clear namespace separation prevents tag collision across categories
- Immutability designation for ORIGIN category is conceptually sound
- DISPUTE category correctly recognizes multi-verifier scenarios as distinct concern
- Resolution types map cleanly to authority levels (auto → single → consensus → override)
- Additive nature preserves historical state transitions

## Issues Found

| Issue | Severity | Category Affected | Proposed Fix |
|-------|----------|-------------------|--------------|
| Mixed abstraction levels in PROCESSING | High | PROCESSING | Split into PROCESSING_ATTEMPT, PROCESSING_OUTCOME, PROCESSING_CONFIDENCE |
| Conflated lifecycle and actions in VERIFICATION | High | VERIFICATION | Split into VERIFICATION_ASSIGNMENT and VERIFICATION_ACTION |
| Inconsistent pending state representations | Medium | Multiple | Standardize: use explicit `[category]:pending` or `[category]:not_started` |
| Mixed linguistic forms (participles/nouns/adjectives) | Medium | All | Standardize to past participles for states, nouns for types |
| QUEUE overlaps with RESOLUTION conceptually | Medium | QUEUE, RESOLUTION | QUEUE should represent location, not state |
| Missing "in_progress" states | High | PROCESSING, VERIFICATION | Add explicit in-progress markers for active operations |
| `processing:partial` ambiguous | Medium | PROCESSING | Define whether this is outcome or confidence issue |

## Proposed Amendments

### Amendment 1.1: Split PROCESSING into Three Sub-Categories

**Current**: PROCESSING mixes attempt status, outcomes, and confidence
**Proposed**: 
```
PROCESSING_ATTEMPT:
- processing_attempt:not_started
- processing_attempt:in_progress
- processing_attempt:completed
- processing_attempt:skipped

PROCESSING_OUTCOME:
- processing_outcome:success
- processing_outcome:failure
- processing_outcome:partial_success

PROCESSING_CONFIDENCE:
- processing_confidence:high
- processing_confidence:medium
- processing_confidence:low
- processing_confidence:none
```

**Justification**: Each sub-category now represents a single conceptual dimension. Attempt tracks lifecycle, outcome tracks result, confidence tracks quality assessment.

### Amendment 1.2: Split VERIFICATION into Assignment and Action

**Current**: VERIFICATION conflates who/when with what action
**Proposed**:
```
VERIFICATION_ASSIGNMENT:
- verification_assignment:unassigned
- verification_assignment:assigned
- verification_assignment:claimed
- verification_assignment:released

VERIFICATION_ACTION:
- verification_action:pending
- verification_action:reviewed
- verification_action:edited
- verification_action:approved
- verification_action:rejected
- verification_action:deferred
- verification_action:escalated
```

**Justification**: Assignment lifecycle is orthogonal to verification actions. A human can be assigned but not yet review, or can review multiple times.

### Amendment 1.3: Clarify QUEUE as Location, Not State

**Current**: `queue:complete` and `queue:archive` are states, not locations
**Proposed**: 
```
QUEUE:
- queue:intake (awaiting initial processing)
- queue:processing (in automatic processing)
- queue:verification (awaiting human verification)
- queue:dispute (in dispute resolution)
- queue:complete (in completed items pool)
- queue:archive (in long-term storage)
```
**Justification**: QUEUE should answer "where is this item?" not "what state is it in?" State is derived from other categories.

### Amendment 1.4: Standardize Linguistic Forms

**Current**: Mixed verb forms and parts of speech
**Proposed**: Use consistent past participles for outcomes, present participles for in-progress states, nouns for types/categories
**Justification**: Linguistic consistency aids both human comprehension and machine parsing

## Questions for Other Agents

- **To Systems Architect**: How should we handle the increased number of categories from a storage/query perspective? Should sub-categories share a namespace prefix?
- **To Product/UX Designer**: Is the split between assignment and action helpful or confusing for user-facing workflows?
- **To Data Engineer**: Does separating processing dimensions improve or complicate analytics queries?
- **To Adversarial Reviewer**: Can you find scenarios where splitting categories creates new ambiguities or impossible states?

## Confidence Rating: 6/10

The current proposal has solid foundations but significant structural issues. The conflation of abstraction levels within categories will cause implementation problems and conceptual confusion. However, these are fixable through reorganization rather than fundamental redesign. The six-category structure is sound; the internal organization needs refinement. With amendments applied, confidence would increase to 8/10.

---

# Agent 2: Systems Architect Report

## Analysis Summary

From a technical implementation perspective, the proposed ontology presents both opportunities and challenges. The namespace structure is well-suited for key-value storage and enables efficient querying through prefix matching. However, the current proposal lacks explicit state transition rules, making it difficult to validate tag combinations and detect invalid states programmatically.

The additive nature of tags is architecturally sound for audit trails but creates ambiguity around "current state" determination. For example, if both `processing:attempted` and `processing:succeeded` exist, the system must infer temporal ordering or rely on metadata. The proposal doesn't specify how conflicting tags should be handled—if `verification:approved` and `verification:rejected` both exist, which takes precedence?

Cross-platform implementation requires careful consideration. SQL databases will need junction tables or array columns for tags. TypeScript will benefit from union types for each category. WASM mode using IndexedDB needs efficient tag-based queries without relational capabilities. The current proposal is implementable across all platforms but needs clarification on indexing strategies and query patterns.

## Strengths Identified

- Namespace structure (`category:value`) prevents collision and enables prefix queries
- Additive model supports complete audit trail without deletions
- Categories map cleanly to separate database indexes
- Immutable ORIGIN tags enable efficient caching
- Resolution and dispute states enable clear terminal conditions
- Tag-based system more flexible than rigid state machines

## Issues Found

| Issue | Severity | Category Affected | Proposed Fix |
|-------|----------|-------------------|--------------|
| No explicit state transition rules | Critical | All | Define allowed transitions and mutex groups |
| Ambiguous "current state" with multiple tags | High | All | Add timestamp metadata or explicit "active" marker |
| Missing mutual exclusivity definitions | High | Multiple | Define mutex groups within categories |
| No tag versioning/schema evolution strategy | Medium | All | Add version prefix or migration plan |
| Unclear bulk operation semantics | Medium | All | Define atomic tag addition rules |
| No definition of tag removal semantics | High | All | Clarify if tags can be removed vs superseded |
| Performance implications of many tags unclear | Medium | All | Define cardinality expectations |
| Missing concurrency control | High | VERIFICATION | Define locking mechanism for simultaneous edits |

## Proposed Amendments

### Amendment 2.1: Define Mutex Groups and Transition Rules

**Current**: No specification of mutually exclusive tags or valid transitions
**Proposed**:
```typescript
// Mutex groups (only one tag from each group can be "active")
MutexGroups = {
  origin: ['origin:ingested', 'origin:uploaded', 'origin:resubmitted'],
  processing_outcome: ['processing:succeeded', 'processing:failed', 'processing:partial'],
  resolution: ['resolution:pending', 'resolution:resolved_auto', ...],
  // etc.
}

// Transition rules
Transitions = {
  'processing:not_attempted': ['processing:attempted', 'processing:skipped'],
  'processing:attempted': ['processing:succeeded', 'processing:failed', 'processing:partial'],
  'verification:unassigned': ['verification:assigned'],
  'verification:assigned': ['verification:claimed', 'verification:unassigned'],
  // etc.
}
```
**Justification**: Explicit rules enable validation, prevent invalid states, and support automated state machines.

### Amendment 2.2: Add Temporal Metadata Structure

**Current**: Tags are flat key-value without temporal context
**Proposed**:
```typescript
interface TagInstance {
  tag: string;              // e.g., "processing:succeeded"
  added_at: ISO8601;
  added_by: UserId | 'system';
  supersedes?: string[];    // Tags this replaces in its mutex group
  active: boolean;          // Current state vs historical
}
```
**Justification**: Enables temporal reasoning, audit trails, and unambiguous current state determination without relying on external timestamps.

### Amendment 2.3: Define Tag Lifecycle Operations

**Current**: Only "add tag" operation implied
**Proposed**:
```
Operations:
- ADD_TAG(tag, actor): Adds new tag, validates transitions, updates mutex group
- SUPERSEDE_TAG(old_tag, new_tag, actor): Explicitly replaces tag in mutex group
- DEACTIVATE_TAG(tag, reason): Marks tag as inactive (not removed, for audit)
- BULK_ADD_TAGS(tags[], actor): Atomic addition of multiple tags with validation
```
**Justification**: Clear operations enable consistent implementation across platforms and define concurrency semantics.

### Amendment 2.4: Indexing Strategy

**Current**: No guidance on query optimization
**Proposed**:
```sql
-- SQL implementation
CREATE TABLE item_tags (
  item_id UUID,
  tag_category VARCHAR(50),  -- 'origin', 'processing', etc.
  tag_value VARCHAR(100),    -- 'uploaded', 'succeeded', etc.
  added_at TIMESTAMP,
  active BOOLEAN DEFAULT true,
  PRIMARY KEY (item_id, tag_category, tag_value, added_at)
);
CREATE INDEX idx_active_tags ON item_tags(item_id) WHERE active = true;
CREATE INDEX idx_category_value ON item_tags(tag_category, tag_value) WHERE active = true;
```

```typescript
// IndexedDB implementation (WASM)
const schema = {
  items: '++id, *tags, &[origin_tag], [queue_tag+resolution_tag]',
  // Multi-entry index on tags array for any-tag queries
  // Compound index on common query patterns
}
```
**Justification**: Anticipates common query patterns (all items with tag X, items in queue Y with resolution Z) and optimizes accordingly.

### Amendment 2.5: Cardinality Constraints

**Current**: Unclear how many tags from each category an item can have
**Proposed**:
```
Category Cardinality:
- ORIGIN: exactly 1 (immutable)
- PROCESSING_ATTEMPT: 0-1 active (lifecycle)
- PROCESSING_OUTCOME: 0-1 active (latest result)
- PROCESSING_CONFIDENCE: 0-1 active (latest assessment)
- VERIFICATION_ASSIGNMENT: 0-1 active per verifier
- VERIFICATION_ACTION: 0-N active (multiple actions possible)
- RESOLUTION: exactly 1 active
- DISPUTE: 0-1 active (not applicable in single-verifier)
- QUEUE: exactly 1 active (current location)
```
**Justification**: Defines expected tag counts, enables validation, clarifies storage requirements.

## Proposed Amendments (continued)

### Amendment 2.6: State Derivation Functions

**Current**: No clear mapping from tags to user-facing states
**Proposed**:
```typescript
function deriveWorkflowState(tags: TagInstance[]): WorkflowState {
  const active = tags.filter(t => t.active);
  
  if (hasTag(active, 'resolution:resolved_*')) return 'COMPLETE';
  if (hasTag(active, 'dispute:split')) return 'IN_DISPUTE';
  if (hasTag(active, 'verification:claimed')) return 'IN_REVIEW';
  if (hasTag(active, 'processing_attempt:in_progress')) return 'PROCESSING';
  if (hasTag(active, 'queue:intake')) return 'PENDING_INTAKE';
  
  // ... comprehensive state derivation logic
}
```
**Justification**: Provides canonical state interpretation, ensures consistency across UI and API, enables testing.

## Questions for Other Agents

- **To Domain Modeler**: Do the proposed mutex groups and transition rules preserve your ontological structure?
- **To Product/UX Designer**: Are the derived workflow states sufficient for user-facing displays, or do you need additional computed states?
- **To Data Engineer**: Do the indexing strategies support your anticipated analytics queries efficiently?
- **To Adversarial Reviewer**: Can you find race conditions in concurrent tag additions that would violate constraints?

## Confidence Rating: 5/10

The current proposal is a good conceptual foundation but critically underspecified for implementation. Without explicit transition rules, mutex groups, and temporal metadata, different implementations will diverge in behavior. The lack of concurrency control for multi-user verification is a significant gap. However, these are specification issues rather than fundamental design flaws. With the proposed amendments defining operational semantics, confidence would increase to 8/10.

---

# Agent 3: Product/UX Designer Report

## Analysis Summary

From a user experience perspective, the proposed tag system has both promising and concerning aspects. The fundamental concern is that tags are implementation details—users think in terms of workflows, actions, and statuses, not tag ontologies. The current proposal risks exposing too much complexity to end users while simultaneously not providing enough clarity about what actions are available in each state.

The six-category structure is logical to engineers but potentially overwhelming to users. Users primarily care about: "What do I need to do with this item?" and "What's the current status?" The distinction between RESOLUTION and QUEUE, or between PROCESSING outcome and confidence, may not be meaningful in user-facing interfaces. However, the underlying tag system can support simplified user-facing states through abstraction.

A critical UX gap is error recovery and workflow escape hatches. If an item gets stuck (e.g., assigned to an inactive user, or processing failed in an unrecoverable way), the tag system doesn't clearly define how to reset or reassign. The `verification:deferred` and `verification:escalated` tags are good starts, but the full escape hatch strategy needs elaboration. Users need clear "undo" and "restart" options that map to valid tag transitions.

## Strengths Identified

- VERIFICATION actions map to clear user intents (approve, reject, defer)
- DISPUTE states give users visibility into consensus status
- QUEUE categories correspond to visible workflow stages
- Escalation pathway exists for exceptions
- Additive tags support "show me history" features
- Deferred action allows users to skip without rejecting

## Issues Found

| Issue | Severity | Category Affected | Proposed Fix |
|-------|----------|-------------------|--------------|
| Tag system exposed vs user-facing states unclear | High | All | Define explicit user-facing state mapping |
| No clear "available actions" per state | Critical | VERIFICATION | Create action-availability matrix |
| Stuck item recovery not defined | High | VERIFICATION, QUEUE | Add reset/reassign mechanisms |
| Too many categories for user comprehension | Medium | All | Group categories for user display |
| Ambiguous feedback on what user should do next | High | VERIFICATION | Add explicit "next action" guidance |
| No progress indication during long processing | Medium | PROCESSING | Add progress sub-states |
| Unclear how users see confidence levels | Medium | PROCESSING | Define confidence display strategy |
| No user notification triggers defined | High | All | Define which tag changes trigger notifications |

## Proposed Amendments

### Amendment 3.1: Define User-Facing State Mapping

**Current**: Six categories of tags, unclear how users see status
**Proposed**:
```typescript
// User-facing states (simplified from tags)
enum UserWorkflowState {
  NEW = "New Upload",                    // queue:intake, no processing
  PROCESSING = "Auto-Processing",        // processing_attempt:in_progress
  READY_FOR_REVIEW = "Ready to Review",  // queue:verification, unassigned
  IN_REVIEW = "You're Reviewing",        // assigned to current user, claimed
  OTHERS_REVIEWING = "Others Reviewing", // assigned to others
  NEEDS_DISPUTE_RESOLUTION = "Disputed", // dispute:split or dispute:escalated
  COMPLETED = "Completed",               // resolution:resolved_*
  FAILED = "Processing Failed",          // processing:failed, not verified
  ARCHIVED = "Archived"                  // queue:archive
}

// Mapping function
function getUserState(item: Item, currentUser: User): UserWorkflowState {
  // Logic to derive user-facing state from tags
}
```
**Justification**: Users need 5-10 clear states, not 30+ possible tag combinations. Derived states can be rich while tags remain granular.

### Amendment 3.2: Available Actions Matrix

**Current**: No specification of what users can do in each state
**Proposed**:
```typescript
type Action = 'claim' | 'review' | 'edit' | 'approve' | 'reject' | 
              'defer' | 'escalate' | 'reassign' | 'restart_processing' | 
              'archive' | 'unarchive';

const ActionAvailability: Record<UserWorkflowState, Action[]> = {
  READY_FOR_REVIEW: ['claim'],
  IN_REVIEW: ['review', 'edit', 'approve', 'reject', 'defer', 'escalate'],
  NEEDS_DISPUTE_RESOLUTION: ['review', 'approve', 'reject', 'escalate'], // admin only
  FAILED: ['restart_processing', 'escalate'], // admin only
  COMPLETED: ['archive'],
  ARCHIVED: ['unarchive'], // admin only
  // etc.
}
```
**Justification**: Explicit action availability prevents confusion, supports dynamic UI (show only available buttons), and defines authorization boundaries.

### Amendment 3.3: Escape Hatches and Reset Mechanisms

**Current**: No clear path to recover from stuck states
**Proposed**:
```
New VERIFICATION_ACTION tags:
- verification_action:unclaimed (user released without action)
- verification_action:reassigned (admin moved to different user)
- verification_action:reset (admin cleared verification history)

New PROCESSING_ATTEMPT tags:
- processing_attempt:restarted (cleared previous attempt, starting fresh)

Workflow:
- If assigned user inactive >48hrs: admin can add "reassigned" tag, update assignment
- If processing failed: admin can add "restarted" tag, trigger new attempt
- If disputed for >72hrs: auto-escalate with "escalated" tag
```
**Justification**: Users and admins need clear escape routes when normal workflow stalls. Timeouts and manual overrides should be explicit in the ontology.

### Amendment 3.4: Notification Trigger Definitions

**Current**: No specification of when users should be alerted
**Proposed**:
```
Notification Triggers:
- Item assigned to user → "You have a new item to review"
- Item claimed by current user → (no notification, user action)
- Item dispute detected → "Item you reviewed is in dispute"
- Item escalated to admin → "Item escalated for your review"
- Processing failed → "Auto-processing failed on [item]"
- Item unassigned from user → "Item [X] was reassigned"

User Preferences:
- Notify on assignment: yes/no
- Notify on dispute: yes/no
- Batch vs immediate notifications
```
**Justification**: Tag changes should map to clear communication events. Users need to know when action is required without being overwhelmed.

### Amendment 3.5: Progress Indication for Long Operations

**Current**: `processing_attempt:in_progress` doesn't show progress
**Proposed**:
```
Add optional progress metadata (not tags):
{
  "processing_progress": {
    "current_step": "OCR extraction",
    "percent_complete": 60,
    "steps_total": 5,
    "estimated_remaining_sec": 45
  }
}

Or use progress sub-tags:
- processing_progress:starting
- processing_progress:ocr_in_progress
- processing_progress:validation_in_progress
- processing_progress:finalizing
```
**Justification**: Users abandon tasks if they don't see progress. Either sub-tags or parallel metadata can provide this feedback.

### Amendment 3.6: Confidence Level Display Strategy

**Current**: Tags like `processing_confidence:low` exist, unclear how users see this
**Proposed**:
```
UI Display:
- High confidence: Green checkmark, "Auto-processing successful"
- Medium confidence: Yellow warning, "Please review carefully"
- Low confidence: Orange alert, "Auto-processing uncertain, manual review critical"
- No confidence: Gray question mark, "Could not assess quality"

Filter Options:
- "Show me low-confidence items" (prioritize manual review)
- "Show me high-confidence items" (quick approval workflow)
```
**Justification**: Confidence tags should directly inform user prioritization and attention allocation. Visual encoding helps users triage efficiently.

## Questions for Other Agents

- **To Systems Architect**: Can the user-facing state derivation functions be performant enough for real-time UI updates?
- **To Domain Modeler**: Do the proposed escape hatch tags (unclaimed, reassigned, restarted) fit the ontological structure?
- **To Data Engineer**: Do notification triggers map cleanly to your event streaming/logging architecture?
- **To Adversarial Reviewer**: What happens if a user clicks "approve" and "reject" simultaneously (UI race condition)?

## Confidence Rating: 6/10

The underlying tag structure is workable but needs significant UX specification before user-facing implementation. The gap between tag granularity and user mental models is the primary concern. The proposed amendments address this by defining clear mappings, actions, and feedback mechanisms. With a complete user-state mapping and action-availability matrix, confidence would increase to 8/10. The system can work well if the implementation layer properly abstracts the tag complexity.

---

# Agent 4: Data Engineer Report

## Analysis Summary

From a data engineering perspective, the proposed tag ontology presents interesting opportunities for flexible querying and analytics but raises concerns about query performance, storage efficiency, and data integrity. The additive tag model is well-suited for temporal analytics and audit trails but may complicate real-time operational queries that need "current state" efficiently.

The primary data concern is query performance at scale. Common queries like "all items in verification queue with processing failures" require joining across multiple tag categories. Without careful indexing and possibly denormalized views, these queries will be slow with large datasets (>100k items). The proposal doesn't specify whether tags should be stored normalized (separate tag records) or denormalized (JSON arrays), which significantly impacts query patterns and performance.

For analytics and reporting, the tag system enables rich historical analysis (e.g., "show me all items where processing confidence improved after manual review"). However, common dashboards will need materialized views or pre-aggregated metrics to avoid full-table scans. The lack of specification around tag cardinality makes it difficult to estimate storage growth—if items accumulate dozens of historical tags, storage and query costs increase linearly.

Data integrity is another concern. The proposal lacks foreign key or referential integrity constraints. For example, who validates that a `verification_assignment:assigned` tag references a valid user? How do we ensure `origin:uploaded` is actually immutable? These integrity rules need to be enforced at the application layer or through database constraints, and the ontology should specify which.

## Strengths Identified

- Additive tags enable complete audit trail without complex versioning
- Tag-based queries support flexible filtering without schema changes
- Historical tag state enables time-series analysis of workflow performance
- Category-based organization supports partitioned indexes
- Immutable ORIGIN tags enable aggressive caching
- Tag model works across SQL, NoSQL, and document stores

## Issues Found

| Issue | Severity | Category Affected | Proposed Fix |
|-------|----------|-------------------|--------------|
| Query performance at scale not addressed | High | All | Define materialized views and indexes |
| Storage model (normalized vs denormalized) unspecified | High | All | Provide reference schemas for SQL/NoSQL |
| Tag cardinality unbounded | Medium | All | Define retention policies for historical tags |
| No referential integrity for user/system references | High | VERIFICATION, ORIGIN | Add foreign key semantics to ontology |
| Aggregation queries require full tag scans | High | All | Define pre-aggregated metrics tables |
| Export format for analytics tools undefined | Medium | All | Specify CSV/JSON export schema |
| No specification of bulk update semantics | Medium | All | Define transaction boundaries for bulk operations |
| Missing event streaming schema | Medium | All | Define event log format for tag changes |

## Proposed Amendments

### Amendment 4.1: Define Reference Schema for SQL

**Current**: No concrete storage model provided
**Proposed**:
```sql
-- Core items table
CREATE TABLE items (
  id UUID PRIMARY KEY,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  content_hash VARCHAR(64) UNIQUE, -- for deduplication
  -- denormalized current state for query performance
  current_queue VARCHAR(50),
  current_resolution VARCHAR(50),
  is_completed BOOLEAN GENERATED ALWAYS AS (current_resolution LIKE 'resolution:resolved_%'),
  -- metadata
  metadata JSONB
);

-- Normalized tags table (audit trail)
CREATE TABLE item_tags (
  id UUID PRIMARY KEY,
  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  tag_category VARCHAR(50) NOT NULL, -- 'origin', 'processing', etc.
  tag_value VARCHAR(100) NOT NULL,   -- 'uploaded', 'succeeded', etc.
  added_at TIMESTAMP NOT NULL DEFAULT NOW(),
  added_by VARCHAR(100) NOT NULL,    -- user_id or 'system'
  active BOOLEAN NOT NULL DEFAULT true,
  superseded_by UUID REFERENCES item_tags(id),
  metadata JSONB
);

-- Indexes for common queries
CREATE INDEX idx_item_tags_active ON item_tags(item_id, tag_category) WHERE active = true;
CREATE INDEX idx_tags_category_value ON item_tags(tag_category, tag_value, added_at) WHERE active = true;
CREATE INDEX idx_items_queue_resolution ON items(current_queue, current_resolution) WHERE NOT is_completed;
CREATE INDEX idx_items_content_hash ON items(content_hash) WHERE content_hash IS NOT NULL;

-- Materialized view for common dashboard queries
CREATE MATERIALIZED VIEW workflow_dashboard AS
SELECT 
  i.current_queue,
  COUNT(*) as total_items,
  COUNT(*) FILTER (WHERE t_conf.tag_value = 'processing_confidence:low') as low_confidence,
  COUNT(*) FILTER (WHERE t_disp.tag_value = 'dispute:split') as disputed,
  AVG(EXTRACT(EPOCH FROM (t_complete.added_at - i.created_at))) as avg_completion_time_sec
FROM items i
LEFT JOIN item_tags t_conf ON t_conf.item_id = i.id AND t_conf.tag_category = 'processing_confidence' AND t_conf.active
LEFT JOIN item_tags t_disp ON t_disp.item_id = i.id AND t_disp.tag_category = 'dispute' AND t_disp.active
LEFT JOIN item_tags t_complete ON t_complete.item_id = i.id AND t_complete.tag_category = 'resolution' AND t_complete.active
GROUP BY i.current_queue;

-- Refresh strategy: REFRESH MATERIALIZED VIEW workflow_dashboard; (run every 5 minutes)
```
**Justification**: Hybrid approach—denormalized current state for fast operational queries, normalized tags for audit trail and analytics. Materialized views for dashboards avoid expensive aggregations.

### Amendment 4.2: Define IndexedDB Schema for WASM

**Current**: No specification for client-side storage
**Proposed**:
```typescript
// Dexie schema
const db = new Dexie('ScreenScrapeDB');
db.version(1).stores({
  items: '++id, content_hash, current_queue, current_resolution, *active_tags, created_at',
  item_tags: '++id, item_id, [tag_category+tag_value], added_at, active',
  // Multi-entry index on active_tags array for quick filtering
});

interface Item {
  id?: number;
  content_hash: string;
  created_at: string;
  updated_at: string;
  current_queue: string;       // denormalized for performance
  current_resolution: string;  // denormalized for performance
  active_tags: string[];       // array of "category:value" for multi-entry index
  metadata: any;
}

interface ItemTag {
  id?: number;
  item_id: number;
  tag_category: string;
  tag_value: string;
  added_at: string;
  added_by: string;
  active: boolean;
  superseded_by?: number;
  metadata?: any;
}

// Query examples
const itemsInReview = await db.items
  .where('active_tags')
  .equals('queue:verification')
  .and(item => item.current_resolution === 'resolution:pending')
  .toArray();
```
**Justification**: IndexedDB requires denormalization for performance. Active tags array enables efficient multi-tag queries without joins.

### Amendment 4.3: Tag Retention and Archival Policy

**Current**: Unbounded tag growth over time
**Proposed**:
```
Retention Policy:
- Active tags: Retained indefinitely
- Superseded tags: Retained for 90 days after supersession
- Tags on completed items: Retained for 1 year after resolution
- Tags on archived items: Compressed to summary metadata

Summary Metadata on Archive:
{
  "workflow_summary": {
    "origin": "uploaded",
    "processing_attempts": 2,
    "final_processing_outcome": "succeeded",
    "verification_count": 3,
    "final_resolution": "resolved_consensus",
    "total_duration_hours": 48.5,
    "tag_count_peak": 12,
    "tag_history_compressed": "s3://archives/item-123-tags.json.gz"
  }
}
```
**Justification**: Limits storage growth while preserving essential audit trail. Compressed archives available for compliance needs.

### Amendment 4.4: Referential Integrity Constraints

**Current**: No validation that tag references are valid
**Proposed**:
```sql
-- User references in tags
CREATE TABLE users (
  user_id VARCHAR(100) PRIMARY KEY,
  username VARCHAR(255) NOT NULL,
  is_active BOOLEAN DEFAULT true
);

-- Validation: added_by must reference valid user or 'system'
ALTER TABLE item_tags ADD CONSTRAINT fk_added_by 
  FOREIGN KEY (added_by) REFERENCES users(user_id)
  ON DELETE RESTRICT; -- prevent deleting users with tag history

-- Application-level validation
function validateTagAddition(tag: TagInstance, item: Item): boolean {
  // Origin tags: only one, immutable
  if (tag.tag_category === 'origin' && item.hasOriginTag()) {
    throw new Error('Origin tag is immutable');
  }
  
  // Verification assignment: must reference active user
  if (tag.tag_value.includes('assigned') && !isActiveUser(tag.metadata.user_id)) {
    throw new Error('Cannot assign to inactive user');
  }
  
  // Mutex group validation
  if (violatesMutexGroup(tag, item.activeTags)) {
    throw new Error('Tag conflicts with existing tag in mutex group');
  }
  
  return true;
}
```
**Justification**: Prevents orphaned references and enforces ontology rules at data layer, not just application layer.

### Amendment 4.5: Analytics Export Schema

**Current**: No standard export format for BI tools
**Proposed**:
```json
// JSON export format for analytics
{
  "export_metadata": {
    "export_date": "2025-11-25T10:30:00Z",
    "item_count": 5000,
    "date_range": {"start": "2025-01-01", "end": "2025-11-25"},
    "schema_version": "1.0"
  },
  "items": [
    {
      "item_id": "uuid-123",
      "created_at": "2025-11-20T08:15:00Z",
      "completed_at": "2025-11-22T14:30:00Z",
      "duration_hours": 54.25,
      "current_state": {
        "origin": "uploaded",
        "queue": "complete",
        "resolution": "resolved_consensus"
      },
      "processing": {
        "attempts": 1,
        "final_outcome": "succeeded",
        "final_confidence": "high",
        "duration_seconds": 12.5
      },
      "verification": {
        "verifier_count": 3,
        "actions": ["reviewed", "edited", "approved"],
        "consensus_achieved": true,
        "disagreements": 0
      },
      "tags_historical": [
        {"tag": "origin:uploaded", "added_at": "2025-11-20T08:15:00Z"},
        {"tag": "processing_attempt:in_progress", "added_at": "2025-11-20T08:15:05Z"},
        // ... full history
      ]
    }
  ]
}
```

```csv
# CSV export format (flattened)
item_id,created_at,completed_at,duration_hours,origin,queue,resolution,processing_attempts,processing_outcome,processing_confidence,verifier_count,consensus_achieved,disagreement_count
uuid-123,2025-11-20T08:15:00Z,2025-11-22T14:30:00Z,54.25,uploaded,complete,resolved_consensus,1,succeeded,high,3,true,0
```
**Justification**: Standardized export formats enable integration with Tableau, PowerBI, Jupyter notebooks, and custom analytics tools.

### Amendment 4.6: Event Streaming Schema

**Current**: No specification for real-time event processing
**Proposed**:
```json
// Event schema for Kafka/RabbitMQ/WebSocket
{
  "event_type": "tag_added",
  "event_id": "uuid-event-789",
  "timestamp": "2025-11-25T10:30:15.123Z",
  "item_id": "uuid-item-123",
  "actor": "user-456",
  "payload": {
    "tag": {
      "category": "verification_action",
      "value": "approved",
      "added_at": "2025-11-25T10:30:15.120Z",
      "metadata": {"confidence": 0.95}
    },
    "item_state_before": {
      "queue": "verification",
      "resolution": "pending"
    },
    "item_state_after": {
      "queue": "verification",
      "resolution": "resolved_single"
    }
  }
}
```
**Justification**: Enables real-time dashboards, WebSocket notifications, and event-driven workflows. Before/after state simplifies consumer logic.

## Questions for Other Agents

- **To Systems Architect**: Do the proposed indexes cover your anticipated query patterns, or are additional compound indexes needed?
- **To Product/UX Designer**: Does the analytics export schema capture the metrics you need for user-facing dashboards?
- **To Domain Modeler**: Does the retention policy's compression to summary metadata lose critical ontological information?
- **To Adversarial Reviewer**: Can you find scenarios where denormalized current state gets out of sync with normalized tag history?

## Confidence Rating: 5/10

The tag ontology is conceptually sound but severely underspecified for production data engineering. Without concrete schemas, indexing strategies, and retention policies, implementations will vary wildly in performance and reliability. The hybrid normalized/denormalized approach I've proposed is battle-tested but needs validation against actual query patterns. Storage costs could spiral without retention policies. With the proposed amendments defining schemas, indexes, and retention, confidence would increase to 8/10.

---

# Agent 5: Adversarial Reviewer Report

## Analysis Summary

As the adversarial reviewer, my role is to find holes, edge cases, and failure modes in the proposed ontology. After thorough examination, I've identified numerous scenarios where the current proposal breaks down, creates ambiguity, or enables gaming/exploitation. The fundamental issue is that the proposal optimizes for the "happy path" while insufficiently specifying error handling, concurrent access, race conditions, and malicious/accidental misuse.

The most critical gap is concurrency control. Consider: User A claims an item for review while User B simultaneously claims it (distributed system, slight network delay). Both users now have `verification_assignment:claimed` tags with their user IDs. Who actually owns it? The ontology doesn't specify. Similarly, if auto-processing adds `processing:succeeded` while a human simultaneously adds `processing:failed` (perhaps manually inspecting logs), which takes precedence? Without explicit conflict resolution rules, implementations will diverge.

The additive tag model, while great for audit trails, creates opportunities for "tag pollution"—intentional or accidental addition of contradictory tags that make state indeterminate. An admin could add both `resolution:resolved_consensus` and `resolution:unresolvable`, effectively bricking the item's state. The proposal lacks defensive mechanisms against this. Additionally, the immutability of ORIGIN tags isn't enforced—nothing prevents re-adding `origin:uploaded` later, violating the immutability claim.

Edge cases around state transitions are also problematic. What happens when: processing succeeds then crashes during database write (partial state)? User approves item then immediately requests to undo (no rollback mechanism)? Item is in dispute but all verifiers leave the organization (orphaned dispute)? Item is resubmitted after archival (lifecycle restart)? These scenarios need explicit ontological support.

## Strengths Identified

- Additive model prevents accidental data loss
- Multiple resolution types acknowledge different authority levels
- Escalation pathway exists for exceptions
- Dispute states enable deadlock detection
- Queue categories support workflow routing
- Historical tag retention enables forensics

## Issues Found

| Issue | Severity | Category Affected | Proposed Fix |
|-------|----------|-------------------|--------------|
| No concurrency control for simultaneous claims | Critical | VERIFICATION | Add optimistic locking or claim tokens |
| Contradictory tags can coexist | Critical | All | Add validation layer preventing contradictions |
| ORIGIN immutability not enforced | High | ORIGIN | Technical enforcement + checksums |
| No rollback/undo mechanism | High | VERIFICATION | Add compensating actions |
| Orphaned disputes when users leave | High | DISPUTE | Add auto-reassignment rules |
| Processing crash during tag write | High | PROCESSING | Add transaction boundaries |
| Resubmission after archival undefined | Medium | ORIGIN, QUEUE | Define lifecycle restart rules |
| Tag injection attacks | High | All | Add input validation + schema enforcement |
| No rate limiting on tag additions | Medium | All | Prevent DOS via tag spam |
| Bulk operations can violate constraints | High | All | Add batch validation |
| Confidence changes after resolution | Medium | PROCESSING | Define whether post-resolution updates allowed |
| Item deleted mid-verification | High | All | Define cascade delete vs soft delete |
| Time-of-check-time-of-use races | Critical | VERIFICATION | Add atomic compare-and-swap |

## Proposed Amendments

### Amendment 5.1: Optimistic Locking for Concurrent Access

**Current**: No concurrency control mechanism
**Proposed**:
```typescript
interface Item {
  id: string;
  version: number; // incremented on every tag addition
  lock_token?: string; // UUID for exclusive operations
  locked_at?: ISO8601;
  locked_by?: UserId;
}

// Claim operation with locking
async function claimItem(itemId: string, userId: string): Result {
  const item = await getItem(itemId);
  
  // Check if already locked
  if (item.lock_token && (Date.now() - item.locked_at) < LOCK_TIMEOUT_MS) {
    return Error('Item locked by another user');
  }
  
  // Atomic compare-and-swap
  const lockToken = generateUUID();
  const updated = await updateItemAtomic(
    itemId, 
    { version: item.version },
    { 
      version: item.version + 1,
      lock_token: lockToken,
      locked_at: now(),
      locked_by: userId
    }
  );
  
  if (!updated) {
    return Error('Concurrent modification detected, retry');
  }
  
  // Now safe to add claim tag
  await addTag({
    tag: 'verification_assignment:claimed',
    item_id: itemId,
    added_by: userId,
    version_when_added: item.version + 1
  });
  
  return Success(lockToken);
}

// Release lock when user submits or navigates away
async function releaseItem(itemId: string, lockToken: string) {
  await updateItemAtomic(
    itemId,
    { lock_token: lockToken },
    { lock_token: null, locked_at: null, locked_by: null }
  );
}
```
**Justification**: Prevents double-claim races, ensures only one user modifies item at a time, automatic timeout for abandoned claims.

### Amendment 5.2: Tag Validation Layer

**Current**: Any tag can be added without validation
**Proposed**:
```typescript
class TagValidator {
  validateTagAddition(tag: TagInstance, item: Item): ValidationResult {
    const activeTags = item.tags.filter(t => t.active);
    
    // Rule 1: ORIGIN immutability
    if (tag.tag_category === 'origin' && hasOriginTag(activeTags)) {
      return Invalid('Origin tag already set and is immutable');
    }
    
    // Rule 2: Mutex group enforcement
    const mutexConflict = findMutexConflict(tag, activeTags);
    if (mutexConflict && !tag.supersedes) {
      return Invalid(`Conflicts with existing tag: ${mutexConflict}`);
    }
    
    // Rule 3: State transition validation
    if (!isValidTransition(activeTags, tag)) {
      return Invalid(`Invalid transition: cannot go from ${getCurrentState(activeTags)} to ${tag.tag}`);
    }
    
    // Rule 4: Authority validation
    if (requiresAdminPermission(tag) && !tag.added_by.isAdmin()) {
      return Invalid('This tag requires admin privileges');
    }
    
    // Rule 5: Referential integrity
    if (tag.metadata?.user_id && !userExists(tag.metadata.user_id)) {
      return Invalid('Referenced user does not exist');
    }
    
    // Rule 6: Schema validation
    if (!matchesTagSchema(tag)) {
      return Invalid('Tag does not match schema');
    }
    
    return Valid();
  }
}

// Apply before every tag addition
async function addTag(tag: TagInstance): Result {
  const item = await getItem(tag.item_id);
  const validation = validator.validateTagAddition(tag, item);
  
  if (!validation.valid) {
    throw new ValidationError(validation.error);
  }
  
  return await insertTag(tag);
}
```
**Justification**: Prevents contradictory states, enforces immutability, validates transitions, ensures authority checks happen before writes.

### Amendment 5.3: Compensating Actions for Undo

**Current**: No mechanism to reverse actions
**Proposed**:
```
New VERIFICATION_ACTION tags:
- verification_action:approval_reversed (admin undoes approval)
- verification_action:rejection_reversed (admin undoes rejection)

New PROCESSING_ATTEMPT tags:
- processing_attempt:cancelled (stop in-progress processing)

Undo Mechanism:
1. User clicks "Undo approval" within 5 minutes
2. System checks if item state has progressed (consensus calculated, etc.)
3. If safe to undo:
   - Add "approval_reversed" tag (supersedes "approved")
   - Decrement verification count
   - Reset resolution to "pending"
   - Notify other verifiers
4. If unsafe (consensus already calculated):
   - Require admin escalation
   - Admin adds "approval_reversed" + "resolution:pending" + "requires_re_consensus"
```
**Justification**: Humans make mistakes. A safe undo window prevents forced escalation for simple errors. Audit trail preserved.

### Amendment 5.4: Orphaned Dispute Resolution

**Current**: No handling when all verifiers of a disputed item become inactive
**Proposed**:
```
Automated Orphan Detection:
- Cron job runs daily
- Finds items with dispute:split AND all verifiers inactive >30 days
- Automatically adds dispute:escalated tag
- Assigns to dispute_resolution_pool (admin group)
- Notification: "Orphaned dispute auto-escalated: Item #123"

Manual Reassignment:
- Admin can add verification_assignment:reassigned tag
- Removes all existing verifier assignments
- Resets verification count
- Item goes back to queue:verification
- Original verifications preserved but marked inactive
```
**Justification**: Prevents items from being permanently stuck in dispute due to user turnover. Automated escalation ensures nothing lost.

### Amendment 5.5: Transactional Tag Operations

**Current**: Tag addition not atomic with state updates
**Proposed**:
```typescript
// Use database transactions
async function approveItem(itemId: string, userId: string, data: any) {
  return await db.transaction(async (tx) => {
    // 1. Verify item state
    const item = await tx.items.findOne(itemId);
    if (item.current_resolution !== 'resolution:pending') {
      throw new Error('Item already resolved');
    }
    
    // 2. Add approval tag
    await tx.item_tags.insert({
      item_id: itemId,
      tag_category: 'verification_action',
      tag_value: 'approved',
      added_by: userId,
      added_at: now(),
      active: true
    });
    
    // 3. Update item verification count
    await tx.items.update(itemId, {
      current_annotation_count: item.current_annotation_count + 1,
      version: item.version + 1
    });
    
    // 4. If quorum reached, update resolution
    if (item.current_annotation_count + 1 >= item.required_annotations) {
      await tx.item_tags.insert({
        item_id: itemId,
        tag_category: 'resolution',
        tag_value: 'resolved_single',
        added_by: 'system',
        added_at: now(),
        active: true
      });
      await tx.items.update(itemId, {
        current_resolution: 'resolution:resolved_single'
      });
    }
    
    // All or nothing - if any step fails, rollback
  });
}
```
**Justification**: Ensures tag additions and state updates happen atomically. Prevents partial state where tag exists but counters not updated.

### Amendment 5.6: Resubmission Lifecycle

**Current**: Unclear what happens when archived item is resubmitted
**Proposed**:
```
Resubmission Rules:
1. If item has origin:uploaded AND current_queue = archive:
   - Admin can add origin:resubmitted (supersedes uploaded, breaking immutability intentionally)
   - System adds processing_attempt:restarted
   - System adds queue:intake
   - Previous tags marked as "archived_generation"
   - New "generation_id" field tracks lifecycle iteration

2. Item now has two tag generations:
   - Generation 1: original workflow tags (archived)
   - Generation 2: resubmission workflow tags (active)

3. Analytics can compare generations:
   - Did processing improve on second attempt?
   - Was consensus easier or harder?
```
**Justification**: Acknowledges that "immutability" sometimes needs controlled violation. Generation tracking preserves history while allowing restart.

### Amendment 5.7: Tag Schema Enforcement

**Current**: No prevention of malformed tags
**Proposed**:
```typescript
// Strict tag schema
const TAG_SCHEMA = {
  origin: ['ingested', 'uploaded', 'resubmitted'],
  processing_attempt: ['not_started', 'in_progress', 'completed', 'skipped', 'restarted'],
  processing_outcome: ['success', 'failure', 'partial_success'],
  // ... complete enumeration
};

function validateTagSchema(tag: string): boolean {
  const [category, value] = tag.split(':');
  
  if (!TAG_SCHEMA[category]) {
    throw new Error(`Unknown tag category: ${category}`);
  }
  
  if (!TAG_SCHEMA[category].includes(value)) {
    throw new Error(`Unknown tag value: ${value} for category ${category}`);
  }
  
  return true;
}

// Database constraint
CREATE TABLE item_tags (
  -- ...
  tag_category VARCHAR(50) NOT NULL CHECK (tag_category IN ('origin', 'processing_attempt', ...)),
  tag_value VARCHAR(100) NOT NULL,
  CONSTRAINT valid_tag_combo CHECK (
    (tag_category = 'origin' AND tag_value IN ('ingested', 'uploaded', 'resubmitted')) OR
    (tag_category = 'processing_attempt' AND tag_value IN ('not_started', 'in_progress', ...)) OR
    -- ... complete validation
  )
);
```
**Justification**: Prevents typos, injection attacks, and schema drift. Database-level enforcement as last line of defense.

### Amendment 5.8: Rate Limiting and DOS Prevention

**Current**: No protection against tag spam
**Proposed**:
```typescript
// Rate limiting per user per item
const RATE_LIMITS = {
  tag_additions_per_item_per_user_per_hour: 50,
  item_claims_per_user_per_hour: 100,
  bulk_operations_per_user_per_hour: 10
};

async function addTagWithRateLimit(tag: TagInstance): Result {
  const recentTags = await getTagAdditions({
    item_id: tag.item_id,
    added_by: tag.added_by,
    since: Date.now() - 3600000 // last hour
  });
  
  if (recentTags.length >= RATE_LIMITS.tag_additions_per_item_per_user_per_hour) {
    throw new RateLimitError('Too many tag additions, please wait');
  }
  
  return await addTag(tag);
}
```
**Justification**: Prevents malicious or buggy code from creating millions of tags, degrading performance and storage.

## Edge Case Scenarios

### Scenario 1: Partial Processing Success Then Crash
```
Timeline:
1. Processing starts: add "processing_attempt:in_progress"
2. OCR succeeds: metadata updated with extracted data
3. Validation starts
4. Server crashes before validation completes
5. On restart: Item has "processing_attempt:in_progress" but no outcome tag

Resolution:
- Startup check: Find all items with "in_progress" tags older than 5 minutes
- Add "processing_attempt:failed" with reason "crashed"
- Add "processing_outcome:partial_success" if metadata has some results
- Add "queue:verification" to route to human review
```

### Scenario 2: Concurrent Approval and Rejection
```
Timeline:
1. User A clicks "Approve" at T+0ms
2. User B clicks "Reject" at T+5ms (slight delay)
3. Both requests hit server nearly simultaneously
4. Without locking: both tags added

Resolution:
- Optimistic locking (Amendment 5.1) prevents this
- First request gets lock, second fails with "concurrent modification"
- Second user sees "Item already reviewed by User A" error
- Second user can add "verification_action:escalated" if they disagree
```

### Scenario 3: Consensus Calculated, Then New Verifier Added
```
Timeline:
1. Three users verify item: consensus reached
2. Add "dispute:unanimous" and "resolution:resolved_consensus"
3. Admin realizes fourth verifier should review
4. Admin manually assigns fourth verifier
5. Fourth verifier submits different values

Resolution:
- System detects: resolution already set
- Adding new verification requires "resolution:pending" to be re-added (superseding resolved_consensus)
- Add "requires_re_consensus" flag
- Recalculate consensus with all four verifications
- Update resolution accordingly
- Audit log shows consensus was recalculated
```

### Scenario 4: Item Deleted During Active Verification
```
Timeline:
1. User claims item for review
2. Admin deletes item (wrong upload, duplicate, etc.)
3. User submits verification
4. Verification fails: item not found

Resolution Option 1 (Soft Delete):
- Items never truly deleted, just tagged "deleted:true"
- Verification still saves, but marked "orphaned"
- User notified: "Item was deleted during your review"

Resolution Option 2 (Cascade Delete):
- Item deletion cascades to tags (foreign key)
- User submission fails gracefully
- User notified: "Item no longer exists"
- In-progress work lost (acceptable if item was truly invalid)

Proposed: Soft delete for 30 days, then hard delete
```

### Scenario 5: User Assigned but Never Claims
```
Timeline:
1. Item assigned to User A: "verification_assignment:assigned"
2. User A never claims (on vacation, forgot, etc.)
3. Item stuck in assigned state indefinitely

Resolution:
- Timeout rule: if assigned >48 hours without claim, auto-unassign
- Add "verification_assignment:auto_released" tag
- Add "queue:verification" (back to pool)
- Notification to admin: "User A has multiple abandoned assignments"
- System can temporarily deprioritize assigning to User A
```

## Questions for Other Agents

- **To Domain Modeler**: Do the compensating action tags (approval_reversed, etc.) fit your ontological structure, or do they violate category purity?
- **To Systems Architect**: Is optimistic locking with version numbers the right approach, or should we use pessimistic locking or distributed locks (Redis)?
- **To Product/UX Designer**: How should users be notified when their action fails due to concurrent modification? Retry automatically or prompt?
- **To Data Engineer**: Do transaction boundaries for multi-tag operations significantly impact write throughput in your experience?

## Confidence Rating: 3/10

The current proposal is fundamentally underspecified for production use. It handles happy paths adequately but fails on edge cases, concurrency, and error recovery. Without explicit conflict resolution, locking mechanisms, validation layers, and compensating actions, different implementations will behave unpredictably under load or adversarial use. The issues I've identified aren't minor—they're critical for reliability.

However, these are solvable problems. The ontology itself is sound; it needs operational rigor. With all proposed amendments (locking, validation, undo, orphan handling, transactions, schema enforcement, rate limiting), confidence would increase to 7/10. The remaining 3 points would require real-world testing to uncover additional edge cases.

---

# Consensus Synthesis Report

## Agreement Summary

| Agent | Confidence | Key Concerns |
|-------|------------|--------------|
| Domain Modeler | 6/10 | Abstraction level mixing, inconsistent linguistic forms, missing primitives |
| Systems Architect | 5/10 | No state transition rules, missing mutex groups, unclear temporal metadata |
| Product/UX Designer | 6/10 | Tag complexity vs user mental models, missing action-availability matrix |
| Data Engineer | 5/10 | Query performance at scale, no concrete schemas, unbounded tag growth |
| Adversarial Reviewer | 3/10 | Concurrency control absent, contradictory states possible, missing error recovery |

**Average Confidence: 5.0/10** - Consensus NOT reached (threshold: all agents ≥7/10)

## Unanimous Agreements

All agents agreed on these fundamental points:

1. **Namespace structure is sound**: The `category:value` pattern prevents collision and enables efficient querying
2. **Additive model valuable**: Historical tag preservation enables audit trails and temporal analytics
3. **Six-category structure logical**: ORIGIN, PROCESSING, VERIFICATION, RESOLUTION, DISPUTE, QUEUE represent distinct conceptual dimensions
4. **Immutable ORIGIN correct**: Setting origin once prevents confusion about item provenance
5. **Missing operational semantics**: All agents identified gaps in state transitions, mutex groups, or conflict resolution
6. **Cross-platform feasibility**: Tag model works across SQL, NoSQL, IndexedDB with appropriate indexing

## Contested Points

| Point | Positions | Resolution |
|-------|-----------|------------|
| **Split PROCESSING and VERIFICATION into sub-categories?** | Domain Modeler: Yes (purity), Systems Architect: Yes (mutex clarity), Product/UX: Concerned about UI complexity | **ACCEPT with caveat**: Split internally, but provide combined view for users. Use dot notation: `processing.attempt:in_progress`, `processing.outcome:success` |
| **Denormalize current state for performance?** | Data Engineer: Yes (required for scale), Domain Modeler: Concerned about sync, Adversarial: Will get out of sync | **ACCEPT with safeguards**: Denormalize current queue/resolution, but use triggers/transactions to ensure sync. Periodic consistency checks. |
| **Optimistic vs pessimistic locking** | Systems Architect: Version-based optimistic, Adversarial: Needs explicit locks | **HYBRID**: Optimistic locking (version) for tag additions, pessimistic locking (tokens) for multi-step operations like verification submission |
| **User-facing state abstraction** | Product/UX: Essential (5-10 states), Domain Modeler: Risks hiding important distinctions | **ACCEPT**: Define derived user states in addition to tags. Tags are ground truth, user states are projections |
| **Tag retention policy** | Data Engineer: Compress after 90 days, Adversarial: Need full history for forensics | **COMPROMISE**: Retain full history for 1 year, compress to summary after, keep compressed archives indefinitely |

## Critical Missing Elements Identified

1. **State Transition Rules**: No agent found these acceptable without explicit transition definitions
2. **Mutex Groups**: Universal agreement needed to prevent contradictory states
3. **Temporal Metadata**: Required for determining current state from additive tags
4. **Concurrency Control**: Critical gap identified by multiple agents
5. **Validation Layer**: Necessary to enforce ontology rules programmatically
6. **Error Recovery**: Missing undo, reassignment, and stuck-state handling
7. **Concrete Schemas**: Implementation guidance needed for SQL and IndexedDB

## Final Amended Proposal

### Ontology Structure

Tags follow the format: `category.subcategory:value` (subcategory optional)

Each tag instance includes:
```typescript
interface TagInstance {
  tag: string;                    // "processing.outcome:success"
  added_at: ISO8601Timestamp;
  added_by: UserId | 'system';
  active: boolean;                // Current state vs historical
  supersedes?: string[];          // Tags replaced in mutex group
  generation?: number;            // Lifecycle iteration (for resubmissions)
  metadata?: Record<string, any>; // Additional context
}
```

Items track denormalized current state:
```typescript
interface Item {
  id: string;
  version: number;                // Optimistic locking
  content_hash: string;           // Deduplication
  created_at: ISO8601Timestamp;
  updated_at: ISO8601Timestamp;
  
  // Denormalized for query performance (synced via triggers)
  current_origin: string;         // "origin:uploaded"
  current_queue: string;          // "queue:verification"
  current_resolution: string;     // "resolution:pending"
  is_completed: boolean;          // Derived from resolution
  
  // Lock for concurrent operations
  lock_token?: string;
  locked_at?: ISO8601Timestamp;
  locked_by?: UserId;
  
  // Lifecycle tracking
  generation: number;             // For resubmissions
  
  metadata: Record<string, any>;
}
```

---

## Category 1: ORIGIN (Immutable - set once at upload)

**Purpose**: Records how the item entered the system

| Tag | Description | When Set | Mutex Group |
|-----|-------------|----------|-------------|
| `origin:ingested` | Received from upstream system/database | At ingestion | origin |
| `origin:uploaded` | Directly uploaded by user | At upload | origin |
| `origin:resubmitted` | Previously processed, submitted again | At resubmission (controlled immutability break) | origin |

**Rules**:
- Exactly one origin tag required per item per generation
- Immutable within a generation
- Resubmission creates new generation with `origin:resubmitted`
- Enforced via database constraints and application validation

---

## Category 2: PROCESSING

**Purpose**: Tracks automatic processing lifecycle, outcomes, and confidence

### Subcategory 2.1: PROCESSING.ATTEMPT (Lifecycle)

| Tag | Description | When Set | Mutex Group |
|-----|-------------|----------|-------------|
| `processing.attempt:not_started` | Auto-processing not yet attempted | Default on upload | processing_attempt |
| `processing.attempt:in_progress` | Auto-processing currently running | When processing begins | processing_attempt |
| `processing.attempt:completed` | Auto-processing finished (success or failure) | When processing ends | processing_attempt |
| `processing.attempt:skipped` | Auto-processing intentionally bypassed | When admin/user skips | processing_attempt |
| `processing.attempt:restarted` | Previous attempt cleared, starting fresh | When admin retries | processing_attempt |
| `processing.attempt:cancelled` | Stopped mid-execution | When user/admin cancels | processing_attempt |

**Transitions**:
- `not_started` → `in_progress`, `skipped`
- `in_progress` → `completed`, `cancelled`
- `completed` → `restarted`
- `skipped` → `restarted`
- `cancelled` → `restarted`

### Subcategory 2.2: PROCESSING.OUTCOME (Result)

| Tag | Description | When Set | Mutex Group |
|-----|-------------|----------|-------------|
| `processing.outcome:success` | Completed without errors | After successful processing | processing_outcome |
| `processing.outcome:failure` | Threw error / crashed | After failed processing | processing_outcome |
| `processing.outcome:partial_success` | Some extractions succeeded, others failed | After partial processing | processing_outcome |

**Rules**:
- Only set when `processing.attempt:completed`
- Exactly zero or one outcome tag active
- Superseded when `processing.attempt:restarted`

### Subcategory 2.3: PROCESSING.CONFIDENCE (Quality Assessment)

| Tag | Description | When Set | Mutex Group |
|-----|-------------|----------|-------------|
| `processing.confidence:high` | Algorithm confident in results (e.g., >90% OCR confidence) | After processing with high confidence | processing_confidence |
| `processing.confidence:medium` | Some uncertainty (e.g., 70-90% confidence) | After processing with medium confidence | processing_confidence |
| `processing.confidence:low` | Significant uncertainty (e.g., <70% confidence) | After processing with low confidence | processing_confidence |
| `processing.confidence:none` | Cannot assess confidence | When confidence unavailable | processing_confidence |

**Rules**:
- Only set when `processing.outcome:success` or `partial_success`
- Exactly zero or one confidence tag active
- Not applicable to `outcome:failure`

---

## Category 3: VERIFICATION

**Purpose**: Tracks human verification lifecycle and actions

### Subcategory 3.1: VERIFICATION.ASSIGNMENT (Who/When)

| Tag | Description | When Set | Metadata Required | Mutex Group (per verifier) |
|-----|-------------|----------|-------------------|----------------------------|
| `verification.assignment:unassigned` | No human assigned yet | Default state | - | verification_assignment_{verifier_slot} |
| `verification.assignment:assigned` | Assigned to a human for review | When assigned | `verifier_id` | verification_assignment_{verifier_slot} |
| `verification.assignment:claimed` | Human has actively opened item | When user opens item | `verifier_id` | verification_assignment_{verifier_slot} |
| `verification.assignment:released` | User released without action | When user closes without submitting | `verifier_id` | verification_assignment_{verifier_slot} |
| `verification.assignment:auto_released` | System released due to timeout | After 48hr inactivity | `verifier_id`, `reason` | verification_assignment_{verifier_slot} |
| `verification.assignment:reassigned` | Admin moved to different user | When admin reassigns | `old_verifier_id`, `new_verifier_id` | verification_assignment_{verifier_slot} |

**Rules**:
- Multi-verifier systems have multiple assignment tags (one per verifier slot)
- Each verifier has their own mutex group
- Timeouts: assigned→auto_released after 48hrs without claim

### Subcategory 3.2: VERIFICATION.ACTION (What User Did)

| Tag | Description | When Set | Metadata Required | Additive/Mutex |
|-----|-------------|----------|-------------------|----------------|
| `verification.action:pending` | No action taken yet | Default state | - | Mutex per verifier |
| `verification.action:reviewed` | Human viewed the item | When user opens item | `verifier_id` | Additive (can review multiple times) |
| `verification.action:edited` | Human modified the data | When user edits fields | `verifier_id`, `fields_changed` | Additive |
| `verification.action:approved` | Human approved (with/without edits) | When user approves | `verifier_id` | Mutex per verifier |
| `verification.action:rejected` | Human marked as invalid/unusable | When user rejects | `verifier_id`, `reason` | Mutex per verifier |
| `verification.action:deferred` | Human postponed decision | When user defers | `verifier_id`, `reason` | Mutex per verifier |
| `verification.action:escalated` | Human escalated to higher authority | When user escalates | `verifier_id`, `reason` | Mutex per verifier |
| `verification.action:approval_reversed` | Admin undid approval | When admin reverses | `admin_id`, `original_verifier_id` | Supersedes approved |
| `verification.action:rejection_reversed` | Admin undid rejection | When admin reverses | `admin_id`, `original_verifier_id` | Supersedes rejected |

**Rules**:
- `reviewed` and `edited` are additive (can occur multiple times)
- `approved`, `rejected`, `deferred`, `escalated` are mutually exclusive per verifier
- Final actions (approved/rejected) require `claimed` state
- Reversals supersede original action, require admin privileges

---

## Category 4: RESOLUTION (Final State)

**Purpose**: Defines the authoritative completion status

| Tag | Description | When Set | Mutex Group |
|-----|-------------|----------|-------------|
| `resolution:pending` | Not yet resolved | Default state | resolution |
| `resolution:resolved_auto` | Auto-processing accepted, no human needed | When high confidence + auto-approval enabled | resolution |
| `resolution:resolved_single` | Single human verification sufficient | When required verifications reached (typically 1) | resolution |
| `resolution:resolved_consensus` | Multiple humans agreed | When consensus achieved | resolution |
| `resolution:resolved_override` | Authority override (admin, tiebreaker) | When admin resolves dispute | resolution |
| `resolution:unresolvable` | Cannot be resolved (bad data, etc.) | When marked unresolvable | resolution |
| `resolution:requires_reconsensus` | Previous resolution invalidated, needs recalculation | When new verifier added after resolution | resolution |

**Rules**:
- Exactly one resolution tag active
- Once resolved (except pending/requires_reconsensus), typically final
- Transitions from resolved_* back to pending only via admin action with audit log
- Reconsensus triggers consensus recalculation

**Transitions**:
- `pending` → any resolved_* state
- `resolved_*` → `requires_reconsensus` (when verification added)
- `requires_reconsensus` → any resolved_* state
- Any state → `unresolvable` (admin only)

---

## Category 5: DISPUTE (Multi-Verifier Systems)

**Purpose**: Tracks consensus status when multiple verifiers review the same item

| Tag | Description | When Set | Mutex Group |
|-----|-------------|----------|-------------|
| `dispute:not_applicable` | Single-verifier mode | When required_verifications = 1 | dispute |
| `dispute:awaiting_quorum` | Need more verifiers | When < required verifications submitted | dispute |
| `dispute:unanimous` | All verifiers agree exactly | When all verifications match | dispute |
| `dispute:majority` | Majority agreement (e.g., 2/3 agree) | When majority threshold met | dispute |
| `dispute:split` | No clear agreement | When no majority exists | dispute |
| `dispute:escalated` | Sent to higher authority | When admin/system escalates | dispute |
| `dispute:resolved` | Disagreement resolved (by override/re-review) | When dispute resolution completed | dispute |
| `dispute:orphaned_auto_escalated` | All verifiers inactive, auto-escalated | After orphan detection (30 days) | dispute |

**Rules**:
- Only applicable when `required_verifications > 1`
- Recalculated whenever new verification added
- Split → escalated automatically after 72hrs
- Orphaned disputes auto-escalate after 30 days

**Metadata**:
- `disagreement_severity`: minor | moderate | major (based on value differences)
- `consensus_algorithm`: median | mean | mode | majority_vote
- `agreement_percentage`: 0.0-1.0

---

## Category 6: QUEUE (Workflow Location)

**Purpose**: Defines where the item currently sits in the workflow

| Tag | Description | When Set | Mutex Group |
|-----|-------------|----------|-------------|
| `queue:intake` | Awaiting initial triage/processing | On upload | queue |
| `queue:processing` | In automatic processing | When processing starts | queue |
| `queue:verification` | Awaiting human verification | When ready for review | queue |
| `queue:dispute_resolution` | Awaiting dispute resolution | When dispute detected | queue |
| `queue:complete` | Finished, no action needed | When resolved | queue |
| `queue:archive` | Archived/historical | When archived (admin/automatic) | queue |

**Rules**:
- Exactly one queue tag active
- Queue represents physical location in workflow
- Automatically updated based on other tag changes

**Automatic Transitions** (system-managed):
- Upload → `queue:intake`
- Processing starts → `queue:processing`
- Processing completes → `queue:verification`
- Dispute detected → `queue:dispute_resolution`
- Resolution reached → `queue:complete`
- Admin/automatic archival → `queue:archive`

---

## Tag Operation Semantics

### Adding Tags
```typescript
async function addTag(
  itemId: string, 
  tag: string, 
  actor: UserId | 'system',
  metadata?: any
): Promise<Result> {
  return await db.transaction(async (tx) => {
    // 1. Acquire lock (for critical operations)
    const item = await tx.items.findOne(itemId);
    
    // 2. Validate transition
    const validation = validateTransition(item.tags, tag);
    if (!validation.valid) throw new ValidationError(validation.error);
    
    // 3. Check mutex group
    const [category, value] = tag.split(':');
    const mutexGroup = getMutexGroup(category);
    const conflicting = item.tags.find(t => 
      t.active && getMutexGroup(t.category) === mutexGroup && t.tag !== tag
    );
    
    // 4. Add new tag
    const tagInstance = {
      tag,
      added_at: now(),
      added_by: actor,
      active: true,
      supersedes: conflicting ? [conflicting.tag] : [],
      generation: item.generation,
      metadata
    };
    await tx.item_tags.insert(tagInstance);
    
    // 5. Deactivate superseded tags
    if (conflicting) {
      await tx.item_tags.update(conflicting.id, { active: false });
    }
    
    // 6. Update denormalized state (triggers handle this automatically)
    await tx.items.update(itemId, {
      version: item.version + 1,
      updated_at: now()
    });
    
    // 7. Emit event for real-time updates
    await emitEvent('tag_added', { itemId, tag, actor });
    
    return Success(tagInstance);
  });
}
```

### State Derivation
```typescript
function deriveUserWorkflowState(item: Item, currentUser: User): UserWorkflowState {
  const tags = item.tags.filter(t => t.active);
  
  // Check resolution first
  if (hasTag(tags, 'resolution:resolved_*')) return 'COMPLETED';
  if (hasTag(tags, 'resolution:unresolvable')) return 'FAILED';
  
  // Check for disputes
  if (hasTag(tags, 'dispute:split') || hasTag(tags, 'dispute:escalated')) {
    return 'NEEDS_DISPUTE_RESOLUTION';
  }
  
  // Check verification state
  const userAssignment = tags.find(t => 
    t.tag.startsWith('verification.assignment:') && 
    t.metadata?.verifier_id === currentUser.id
  );
  
  if (userAssignment?.tag === 'verification.assignment:claimed') {
    return 'IN_REVIEW';
  } else if (hasTag(tags, 'verification.assignment:assigned')) {
    return 'OTHERS_REVIEWING';
  } else if (hasTag(tags, 'queue:verification')) {
    return 'READY_FOR_REVIEW';
  }
  
  // Check processing state
  if (hasTag(tags, 'processing.attempt:in_progress')) return 'PROCESSING';
  if (hasTag(tags, 'processing.outcome:failure')) return 'PROCESSING_FAILED';
  
  // Default states
  if (hasTag(tags, 'queue:intake')) return 'NEW';
  if (hasTag(tags, 'queue:archive')) return 'ARCHIVED';
  
  return 'UNKNOWN';
}
```

### Concurrency Control
```typescript
// Optimistic locking for tag additions (lightweight)
async function addTagOptimistic(itemId: string, tag: string, actor: string) {
  const item = await getItem(itemId);
  const result = await updateItemAtomic(
    itemId,
    { version: item.version },
    { version: item.version + 1 }
  );
  
  if (!result) {
    throw new ConcurrentModificationError('Item modified by another operation, retry');
  }
  
  await insertTag({ item_id: itemId, tag, added_by: actor });
}

// Pessimistic locking for multi-step operations (heavyweight)
async function claimAndVerifyItem(itemId: string, userId: string, data: any) {
  const lockToken = await acquireLock(itemId, userId, LOCK_TIMEOUT_MS);
  
  try {
    await addTag(itemId, 'verification.assignment:claimed', userId, { verifier_id: userId });
    await addTag(itemId, 'verification.action:reviewed', userId, { verifier_id: userId });
    // ... perform verification
    await addTag(itemId, 'verification.action:approved', userId, { verifier_id: userId });
  } finally {
    await releaseLock(itemId, lockToken);
  }
}
```

### Error Recovery
```typescript
// Startup consistency check
async function checkStuckItems() {
  // Find items with in_progress tags older than 5 minutes
  const stuckItems = await db.item_tags.find({
    tag: 'processing.attempt:in_progress',
    added_at: { $lt: Date.now() - 300000 },
    active: true
  });
  
  for (const tag of stuckItems) {
    await addTag(tag.item_id, 'processing.outcome:failure', 'system', {
      reason: 'Processing timeout or crash',
      original_attempt_at: tag.added_at
    });
    await addTag(tag.item_id, 'queue:verification', 'system');
  }
}

// Orphaned dispute detection (daily cron)
async function escalateOrphanedDisputes() {
  const orphaned = await db.query(`
    SELECT i.id, array_agg(t.metadata->>'verifier_id') as verifiers
    FROM items i
    JOIN item_tags t ON t.item_id = i.id
    WHERE i.current_dispute = 'dispute:split'
      AND t.tag_category = 'verification.assignment'
      AND t.active = true
    GROUP BY i.id
    HAVING every((
      SELECT u.is_active 
      FROM users u 
      WHERE u.user_id = ANY(array_agg(t.metadata->>'verifier_id'))
    ) = false)
    AND i.updated_at < NOW() - INTERVAL '30 days'
  `);
  
  for (const item of orphaned) {
    await addTag(item.id, 'dispute:orphaned_auto_escalated', 'system', {
      original_verifiers: item.verifiers,
      reason: 'All verifiers inactive for 30+ days'
    });
    await addTag(item.id, 'queue:dispute_resolution', 'system');
  }
}
```

---

## Cross-Platform Implementation Guidance

### SQL Schema (PostgreSQL/SQLite)
```sql
CREATE TABLE items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version INTEGER NOT NULL DEFAULT 1,
  content_hash VARCHAR(64) UNIQUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  generation INTEGER NOT NULL DEFAULT 1,
  
  -- Denormalized current state (updated via triggers)
  current_origin VARCHAR(100),
  current_queue VARCHAR(100),
  current_resolution VARCHAR(100),
  is_completed BOOLEAN GENERATED ALWAYS AS (current_resolution LIKE 'resolution:resolved_%') STORED,
  
  -- Locking
  lock_token UUID,
  locked_at TIMESTAMP,
  locked_by VARCHAR(100),
  
  metadata JSONB,
  
  CONSTRAINT valid_origin CHECK (current_origin ~ '^origin:'),
  CONSTRAINT valid_queue CHECK (current_queue ~ '^queue:'),
  CONSTRAINT valid_resolution CHECK (current_resolution ~ '^resolution:')
);

CREATE TABLE item_tags (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  tag VARCHAR(200) NOT NULL,
  tag_category VARCHAR(50) GENERATED ALWAYS AS (split_part(tag, ':', 1)) STORED,
  tag_value VARCHAR(100) GENERATED ALWAYS AS (split_part(tag, ':', 2)) STORED,
  added_at TIMESTAMP NOT NULL DEFAULT NOW(),
  added_by VARCHAR(100) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT true,
  generation INTEGER NOT NULL DEFAULT 1,
  metadata JSONB,
  
  CONSTRAINT fk_added_by FOREIGN KEY (added_by) REFERENCES users(user_id) ON DELETE RESTRICT,
  CONSTRAINT valid_tag_format CHECK (tag ~ '^[a-z_]+(\.[a-z_]+)?:[a-z_]+$')
);

-- Indexes
CREATE INDEX idx_item_tags_active ON item_tags(item_id, tag_category) WHERE active = true;
CREATE INDEX idx_tags_category_value ON item_tags(tag_category, tag_value, added_at) WHERE active = true;
CREATE INDEX idx_items_queue_resolution ON items(current_queue, current_resolution) WHERE NOT is_completed;
CREATE INDEX idx_items_content_hash ON items(content_hash) WHERE content_hash IS NOT NULL;

-- Trigger to update denormalized state
CREATE OR REPLACE FUNCTION update_item_current_state()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.active = true THEN
    UPDATE items SET
      current_origin = CASE WHEN NEW.tag_category = 'origin' THEN NEW.tag ELSE current_origin END,
      current_queue = CASE WHEN NEW.tag_category = 'queue' THEN NEW.tag ELSE current_queue END,
      current_resolution = CASE WHEN NEW.tag_category = 'resolution' THEN NEW.tag ELSE current_resolution END,
      updated_at = NOW()
    WHERE id = NEW.item_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_item_state
AFTER INSERT OR UPDATE ON item_tags
FOR EACH ROW
EXECUTE FUNCTION update_item_current_state();
```

### IndexedDB Schema (WASM/Client-Side)
```typescript
import Dexie, { Table } from 'dexie';

interface Item {
  id?: number;
  version: number;
  content_hash: string;
  created_at: string;
  updated_at: string;
  generation: number;
  
  // Denormalized
  current_origin: string;
  current_queue: string;
  current_resolution: string;
  is_completed: boolean;
  active_tags: string[]; // Multi-entry index
  
  metadata: any;
}

interface ItemTag {
  id?: number;
  item_id: number;
  tag: string;
  tag_category: string;
  tag_value: string;
  added_at: string;
  added_by: string;
  active: boolean;
  generation: number;
  metadata?: any;
}

class ScreenScrapeDB extends Dexie {
  items!: Table<Item>;
  item_tags!: Table<ItemTag>;

  constructor() {
    super('ScreenScrapeDB');
    this.version(1).stores({
      items: '++id, content_hash, current_queue, current_resolution, generation, *active_tags, created_at',
      item_tags: '++id, item_id, [tag_category+tag_value], [item_id+active], added_at, active'
    });
  }
}

const db = new ScreenScrapeDB();

// Example query: Get all items in verification queue that need review
const itemsNeedingReview = await db.items
  .where('active_tags')
  .equals('queue:verification')
  .and(item => item.current_resolution === 'resolution:pending')
  .toArray();
```

### TypeScript Type Definitions
```typescript
// Tag categories
type OriginTag = 'origin:ingested' | 'origin:uploaded' | 'origin:resubmitted';

type ProcessingAttemptTag = 
  | 'processing.attempt:not_started'
  | 'processing.attempt:in_progress'
  | 'processing.attempt:completed'
  | 'processing.attempt:skipped'
  | 'processing.attempt:restarted'
  | 'processing.attempt:cancelled';

type ProcessingOutcomeTag =
  | 'processing.outcome:success'
  | 'processing.outcome:failure'
  | 'processing.outcome:partial_success';

type ProcessingConfidenceTag =
  | 'processing.confidence:high'
  | 'processing.confidence:medium'
  | 'processing.confidence:low'
  | 'processing.confidence:none';

type VerificationAssignmentTag =
  | 'verification.assignment:unassigned'
  | 'verification.assignment:assigned'
  | 'verification.assignment:claimed'
  | 'verification.assignment:released'
  | 'verification.assignment:auto_released'
  | 'verification.assignment:reassigned';

type VerificationActionTag =
  | 'verification.action:pending'
  | 'verification.action:reviewed'
  | 'verification.action:edited'
  | 'verification.action:approved'
  | 'verification.action:rejected'
  | 'verification.action:deferred'
  | 'verification.action:escalated'
  | 'verification.action:approval_reversed'
  | 'verification.action:rejection_reversed';

type ResolutionTag =
  | 'resolution:pending'
  | 'resolution:resolved_auto'
  | 'resolution:resolved_single'
  | 'resolution:resolved_consensus'
  | 'resolution:resolved_override'
  | 'resolution:unresolvable'
  | 'resolution:requires_reconsensus';

type DisputeTag =
  | 'dispute:not_applicable'
  | 'dispute:awaiting_quorum'
  | 'dispute:unanimous'
  | 'dispute:majority'
  | 'dispute:split'
  | 'dispute:escalated'
  | 'dispute:resolved'
  | 'dispute:orphaned_auto_escalated';

type QueueTag =
  | 'queue:intake'
  | 'queue:processing'
  | 'queue:verification'
  | 'queue:dispute_resolution'
  | 'queue:complete'
  | 'queue:archive';

type Tag =
  | OriginTag
  | ProcessingAttemptTag
  | ProcessingOutcomeTag
  | ProcessingConfidenceTag
  | VerificationAssignmentTag
  | VerificationActionTag
  | ResolutionTag
  | DisputeTag
  | QueueTag;

// Mutex group definitions
const MUTEX_GROUPS: Record<string, Tag[]> = {
  origin: ['origin:ingested', 'origin:uploaded', 'origin:resubmitted'],
  processing_attempt: [
    'processing.attempt:not_started',
    'processing.attempt:in_progress',
    'processing.attempt:completed',
    'processing.attempt:skipped',
    'processing.attempt:restarted',
    'processing.attempt:cancelled'
  ],
  processing_outcome: [
    'processing.outcome:success',
    'processing.outcome:failure',
    'processing.outcome:partial_success'
  ],
  // ... etc.
};

// User-facing states
enum UserWorkflowState {
  NEW = 'New Upload',
  PROCESSING = 'Auto-Processing',
  READY_FOR_REVIEW = 'Ready to Review',
  IN_REVIEW = "You're Reviewing",
  OTHERS_REVIEWING = 'Others Reviewing',
  NEEDS_DISPUTE_RESOLUTION = 'Disputed',
  COMPLETED = 'Completed',
  PROCESSING_FAILED = 'Processing Failed',
  ARCHIVED = 'Archived',
  UNKNOWN = 'Unknown State'
}
```

---

## Migration Path from Current Implementation

The current screenshot annotation system uses simpler tags. Migration strategy:

### Phase 1: Additive Migration (No Breaking Changes)
1. Keep existing tags operational
2. Add new tag format alongside old format
3. Write to both formats during transition
4. Read from new format with fallback to old

### Phase 2: Data Migration
```sql
-- Migrate origin tags
INSERT INTO item_tags (item_id, tag, added_by, added_at, active)
SELECT id, 'origin:uploaded', 'migration', created_at, true
FROM items
WHERE EXISTS (SELECT 1 FROM item_tags WHERE item_id = items.id AND tag_value = 'uploaded')
ON CONFLICT DO NOTHING;

-- Migrate processing status
INSERT INTO item_tags (item_id, tag, added_by, added_at, active)
SELECT id, 
  CASE 
    WHEN processing_status = 'completed' THEN 'processing.outcome:success'
    WHEN processing_status = 'failed' THEN 'processing.outcome:failure'
    ELSE 'processing.attempt:not_started'
  END,
  'migration',
  updated_at,
  true
FROM items;

-- Migrate verification status
INSERT INTO item_tags (item_id, tag, added_by, added_at, active, metadata)
SELECT a.screenshot_id,
  'verification.action:approved',
  a.user_id,
  a.created_at,
  true,
  jsonb_build_object('verifier_id', a.user_id)
FROM annotations a;

-- ... etc.
```

### Phase 3: Cutover
1. Deploy new code using new tag format
2. Deprecate old tag writes
3. Monitor for 1 week
4. Remove old tag read logic

### Phase 4: Cleanup (Optional)
1. Archive old tag format data
2. Drop old columns/tables

---

## Validation and Testing Checklist

Before declaring this ontology production-ready, validate:

### Ontological Completeness
- [ ] All workflow states have tag representation
- [ ] All state transitions have explicit paths
- [ ] No ambiguous states (multiple valid interpretations)
- [ ] Terminal states clearly defined
- [ ] Error recovery paths exist for all stuck states

### Technical Correctness
- [ ] Mutex groups prevent contradictory states
- [ ] State transition rules enforced programmatically
- [ ] Concurrency control prevents race conditions
- [ ] Database schemas support all query patterns
- [ ] Indexes optimize common queries
- [ ] Tag cardinality bounds defined

### User Experience
- [ ] User-facing states map clearly to tags
- [ ] Available actions derivable from current state
- [ ] Error messages explain why actions unavailable
- [ ] Undo mechanisms exist for common errors
- [ ] Notifications trigger on correct tag changes

### Data Integrity
- [ ] Foreign key constraints prevent orphaned references
- [ ] Denormalized state syncs correctly with tags
- [ ] Retention policies prevent unbounded growth
- [ ] Export formats support analytics tools
- [ ] Event streams enable real-time updates

### Generalizability
- [ ] Test with screenshot annotation workflow
- [ ] Test with document review workflow
- [ ] Test with data validation workflow
- [ ] Identify domain-specific vs domain-agnostic tags
- [ ] Verify abstractions hold across domains

---

## Consensus Status

**CONSENSUS REACHED: YES** (with amendments)

### Post-Amendment Confidence Scores

| Agent | Confidence | Reasoning |
|-------|------------|-----------|
| Domain Modeler | 8/10 | Subcategories improve purity, dot notation acceptable, compensating actions fit |
| Systems Architect | 8/10 | Mutex groups and transitions defined, locking strategy clear, schemas provided |
| Product/UX Designer | 8/10 | User state mapping addresses complexity, action matrix defined, escape hatches clear |
| Data Engineer | 8/10 | Concrete schemas provided, indexing strategy defined, retention policy specified |
| Adversarial Reviewer | 7/10 | Concurrency control added, validation layer defined, edge cases addressed (remaining concerns need real-world testing) |

**Average Confidence: 7.8/10** - Consensus threshold met

### Remaining Risks (for real-world testing)

1. **Performance at scale**: While indexes are defined, actual performance with 1M+ items and 10M+ tags needs load testing
2. **Additional edge cases**: Real user behavior will uncover scenarios not anticipated in adversarial review
3. **Cross-platform parity**: Ensuring SQL and IndexedDB implementations behave identically requires integration testing
4. **Schema evolution**: First schema change will test migration strategy under production load
5. **User comprehension**: A/B testing needed to validate that user-facing states are intuitive

### Recommended Next Steps

1. **Implement in screenshot annotation system** as pilot (existing codebase, known domain)
2. **Run load tests** with 100k items, 10 concurrent users, measure query performance
3. **Monitor edge cases** in production for 1 month, document any new failure modes
4. **User testing** of simplified states, gather feedback on clarity and actionability
5. **Second domain pilot** (e.g., document review) to validate generalizability
6. **Schema versioning implementation** to test migration strategy
7. **Security audit** of tag validation, especially user input in metadata fields

---

## Appendix: Glossary

**Tag**: A structured label (category:value) attached to an item, tracking workflow state and history

**Tag Instance**: A specific occurrence of a tag with temporal metadata (when added, by whom, is it active)

**Mutex Group**: A set of tags where only one can be active simultaneously (e.g., only one origin tag per item)

**Active Tag**: Current state tag vs historical tag (active=true means this is the current state)

**Supersede**: Replacing one tag with another in a mutex group, deactivating the old while preserving history

**Generation**: Lifecycle iteration for items that are resubmitted, allowing controlled immutability breaks

**Denormalized State**: Current state stored redundantly on item record for query performance (synced via triggers)

**Optimistic Locking**: Concurrency control using version numbers, detecting conflicts at write time

**Pessimistic Locking**: Concurrency control using explicit locks, preventing conflicts by exclusive access

**State Derivation**: Computing user-facing state from combination of active tags

**Compensating Action**: Tag that reverses a previous action while preserving audit trail (e.g., approval_reversed)

**Orphaned Dispute**: Dispute where all verifiers have become inactive, requiring automatic escalation

**Tag Pollution**: Intentional or accidental addition of contradictory tags that create ambiguous state

**Additive Model**: Tags are added, never deleted, preserving complete history

---

*End of Multi-Agent Consensus Report*
*Generated: 2025-11-25*
*Version: 1.0*
*Status: Consensus Reached - Ready for Implementation*
