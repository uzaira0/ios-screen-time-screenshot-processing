# Tag Ontology Design Summary

**Date**: 2025-11-25  
**Status**: Paused - needs further consideration before implementation

## Context

Designing a generalizable tag system for bulk-processing human-verification systems. Primary use case is screenshot annotation (OCR extraction), but should generalize to other domains.

## Two Proposals

### 1. Comprehensive Ontology (50 tags, 6 categories)

From multi-agent consensus analysis. Academically complete but potentially over-engineered.

**Categories**:
- ORIGIN (3): ingested, uploaded, resubmitted
- PROCESSING.ATTEMPT (6): not_started, in_progress, completed, skipped, restarted, cancelled
- PROCESSING.OUTCOME (3): success, failure, partial_success
- PROCESSING.CONFIDENCE (4): high, medium, low, none
- VERIFICATION.ASSIGNMENT (6): unassigned, assigned, claimed, released, auto_released, reassigned
- VERIFICATION.ACTION (9): pending, reviewed, edited, approved, rejected, deferred, escalated, approval_reversed, rejection_reversed
- RESOLUTION (7): pending, resolved_auto, resolved_single, resolved_consensus, resolved_override, unresolvable, requires_reconsensus
- DISPUTE (8): not_applicable, awaiting_quorum, unanimous, majority, split, escalated, resolved, orphaned_auto_escalated
- QUEUE (6): intake, processing, verification, dispute_resolution, complete, archive

**Pros**: Complete audit trail, handles all edge cases, future-proof  
**Cons**: Complex, 50% more storage, harder to implement

### 2. Minimal Ontology (18 tags, 5 categories)

Streamlined version from review round.

**Categories**:
- ORIGIN (1): uploaded
- PROCESSING (4): not_started, success, failed, low_confidence
- VERIFICATION (6): assigned, claimed, approved, rejected, deferred, escalated
- RESOLUTION (4): pending, resolved, override, unresolvable
- DISPUTE (3): unanimous, split, escalated

**Derived (not tags)**:
- `current_queue` - computed from other tags
- `annotation_count` - incremented on approval/rejection
- `is_completed` - derived from resolution

**Pros**: Simple, 50% less storage, faster queries, easier TypeScript  
**Cons**: Less granular history, may need extension later

## Key Design Decisions Pending

1. **Subcategories**: Use `processing.attempt:value` or flat `processing:value`?
2. **QUEUE**: Tag category or derived column?
3. **Granularity**: How much processing/verification history to preserve?
4. **Scope**: Design for screenshot-only or multi-domain from start?

## Recommendation

Start with the **18-tag minimal ontology** for the screenshot annotation system. Extend later if needed. The comprehensive version is documented if requirements grow.

## Files in This Folder

- `SUMMARY.md` - This file
- `021-tag-ontology-multi-agent-consensus.md` - Original prompt
- `021-tag-ontology-multi-agent-consensus-RESULT.md` - Full 5-agent analysis with comprehensive ontology
- `queue_models.py` reference - Existing Python implementation (in `src/screenshot_processor/core/`)

## Next Steps When Ready

1. Decide on minimal vs comprehensive approach
2. Create TypeScript types matching chosen ontology
3. Update IndexedDB schema
4. Integrate into WASM processing pipeline
5. Add UI for tag display
