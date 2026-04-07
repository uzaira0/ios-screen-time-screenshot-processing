<objective>
Refine and finalize a generalizable tag ontology for bulk-processing human-verification systems through sequential multi-agent analysis. Five expert agents with distinct priorities will each analyze the current proposal, write their reports, and contribute to a combined recommendation. Iterate until consensus is reached.

This ontology will be used across multiple webapps that ingest automatically-processed data and delegate human verification tasks. The primitives must be concrete, composable, and support transitions between automatic processing, manual verification, and dispute/consensus resolution.
</objective>

<context>
We are designing a tag system for workflow state management in human-in-the-loop data processing pipelines. The current domain is screenshot annotation (OCR extraction of screen time/battery data), but the system must generalize to any bulk processing → human verification workflow.

The current proposal has 6 primitive categories:
1. ORIGIN - How the item entered the system
2. PROCESSING - What happened during automatic processing
3. VERIFICATION - What humans have done with the item
4. QUEUE - Where the item sits in the workflow
5. RESOLUTION - Final determination state
6. DISPUTE - Multi-verifier agreement state

Key requirements:
- Tags must be additive (history preserved) with clear override semantics
- State should be derivable from tag combinations
- Must support transitions: auto-processing → manual verification → consensus/dispute resolution
- Must work across platforms (Python backend, TypeScript frontend, WASM)
</context>

<current_proposal>
```
## Category 1: ORIGIN (Immutable - set once at upload)
| Tag | Description |
|-----|-------------|
| `origin:ingested` | Received from upstream system/database |
| `origin:uploaded` | Directly uploaded by user |
| `origin:resubmitted` | Previously processed, submitted again |

## Category 2: PROCESSING (Set during automatic processing)
### Attempt
| `processing:attempted` | Auto-processing was run |
| `processing:skipped` | Auto-processing intentionally skipped |
| `processing:not_attempted` | Not yet processed |

### Outcome
| `processing:succeeded` | Completed without errors |
| `processing:failed` | Threw error / crashed |
| `processing:partial` | Some extractions succeeded, others failed |

### Confidence
| `processing:confidence_high` | Algorithm confident in results |
| `processing:confidence_medium` | Some uncertainty |
| `processing:confidence_low` | Significant uncertainty |
| `processing:confidence_unknown` | Cannot assess confidence |

## Category 3: VERIFICATION (Set by human actions)
### Assignment
| `verification:unassigned` | No human assigned yet |
| `verification:assigned` | Assigned to a human for review |
| `verification:claimed` | Human has actively claimed/opened it |

### Action Taken
| `verification:reviewed` | Human has looked at it |
| `verification:edited` | Human modified the data |
| `verification:approved` | Human approved (with or without edits) |
| `verification:rejected` | Human marked as invalid/unusable |
| `verification:deferred` | Human postponed decision |
| `verification:escalated` | Human escalated to higher authority |

## Category 4: RESOLUTION (Final state)
| `resolution:pending` | Not yet resolved |
| `resolution:resolved_auto` | Auto-processing accepted (no human needed) |
| `resolution:resolved_single` | Single human verification sufficient |
| `resolution:resolved_consensus` | Multiple humans agreed |
| `resolution:resolved_override` | Authority override (admin, tiebreaker) |
| `resolution:unresolvable` | Cannot be resolved (bad data, etc.) |

## Category 5: DISPUTE (Multi-verifier systems)
| `dispute:not_applicable` | Single-verifier mode |
| `dispute:awaiting_quorum` | Need more verifiers |
| `dispute:unanimous` | All verifiers agree |
| `dispute:majority` | Majority agreement |
| `dispute:split` | No clear agreement |
| `dispute:escalated` | Sent to higher authority |
| `dispute:resolved` | Disagreement resolved |

## Category 6: QUEUE (Workflow position)
| `queue:inbox` | Awaiting initial triage |
| `queue:auto_processing` | In automatic processing |
| `queue:human_review` | Awaiting human verification |
| `queue:dispute_resolution` | Awaiting dispute resolution |
| `queue:complete` | Finished, no action needed |
| `queue:archive` | Archived/historical |
```
</current_proposal>

<agent_sequence>
Execute each agent sequentially. Each agent must:
1. Thoroughly analyze the current proposal from their unique perspective
2. Identify strengths, weaknesses, gaps, and contradictions
3. Propose specific amendments with justification
4. Rate their confidence in the proposal (1-10)
5. Pass their report to the next agent

After all 5 agents complete, synthesize a final combined report and check for consensus (all agents rate >= 7, no unresolved contradictions). If consensus not reached, iterate with a second round addressing the disagreements.
</agent_sequence>

<agents>
## Agent 1: Domain Modeler
<role>Ontological purist focused on conceptual clarity and correctness</role>
<priorities>
- Categorical purity: Are categories mutually exclusive and collectively exhaustive?
- Semantic precision: Do tag names accurately reflect their meaning?
- Ontological consistency: Are similar concepts treated similarly?
- Abstraction level: Are primitives at the right level of abstraction?
- Avoiding conflation: Are distinct concepts kept separate?
</priorities>
<questions_to_address>
- Are there any category overlaps or boundary ambiguities?
- Are there missing primitive concepts?
- Are any tags at the wrong abstraction level?
- Is the namespace/prefix scheme semantically sound?
- Do the tag names follow consistent linguistic patterns?
</questions_to_address>

## Agent 2: Systems Architect
<role>Technical implementer focused on composability and system design</role>
<priorities>
- Composability: Can tags combine cleanly without conflicts?
- State derivation: Can workflow state be reliably computed from tags?
- Performance: Are there indexing/querying implications?
- Cross-platform: Will this work in Python, TypeScript, WASM, SQL?
- Extensibility: Can domain-specific tags be added without breaking core?
</priorities>
<questions_to_address>
- What are the state transition rules and are they complete?
- Are there any impossible or contradictory tag combinations?
- How should tags be stored (array, set, bitfield, separate columns)?
- What indexes are needed for common queries?
- How do we handle tag versioning/migrations?
</questions_to_address>

## Agent 3: Product/UX Designer
<role>User advocate focused on workflow clarity and usability</role>
<priorities>
- Understandability: Can non-technical users understand the states?
- Workflow clarity: Is it obvious what happens next for any item?
- Error recovery: Can users fix mistakes or recover from wrong states?
- Feedback: Do tags provide sufficient feedback about what happened?
- Simplicity: Is the system as simple as possible but no simpler?
</priorities>
<questions_to_address>
- What does a user need to see vs what's internal bookkeeping?
- Are there too many states that would confuse users?
- How would you explain each queue to a new user?
- What actions should be available from each state?
- Are there missing "escape hatches" for edge cases?
</questions_to_address>

## Agent 4: Data Engineer
<role>Data specialist focused on storage, analytics, and data integrity</role>
<priorities>
- Query patterns: What are the common filters/aggregations?
- Storage efficiency: What's the storage overhead?
- Analytics: Can we answer business questions from tags?
- Audit trail: Is history preserved for compliance/debugging?
- Data integrity: Are there constraints that should be enforced?
</priorities>
<questions_to_address>
- What reports/dashboards need to be built from this data?
- How do we handle bulk state transitions efficiently?
- What's the cardinality of each tag category?
- Should some tags be denormalized for query performance?
- How do we export this data (CSV, API, etc.)?
</questions_to_address>

## Agent 5: Adversarial Reviewer
<role>Devil's advocate finding edge cases, contradictions, and failure modes</role>
<priorities>
- Edge cases: What happens in unusual situations?
- Contradictions: Are there impossible states or circular dependencies?
- Gaming: Can users manipulate the system?
- Failure modes: What breaks when things go wrong?
- Missing states: What real-world situations aren't covered?
</priorities>
<questions_to_address>
- What if processing partially succeeds then crashes?
- What if a user is assigned but never acts?
- What if consensus changes after resolution?
- What if the same item is uploaded twice?
- What happens during system migration/upgrade?
</questions_to_address>
</agents>

<output_format>
For each agent, produce a report with:

```markdown
# Agent [N]: [Role Name] Report

## Analysis Summary
[2-3 paragraph assessment from this perspective]

## Strengths Identified
- [Bullet points]

## Issues Found
| Issue | Severity | Category Affected | Proposed Fix |
|-------|----------|-------------------|--------------|
| ...   | High/Med/Low | ... | ... |

## Proposed Amendments
### Amendment [N.1]: [Title]
**Current**: [What exists now]
**Proposed**: [What it should be]
**Justification**: [Why this change]

### Amendment [N.2]: ...

## Questions for Other Agents
- [Questions that need input from other perspectives]

## Confidence Rating: [1-10]
[Explanation of rating]
```

After all 5 agents, produce:

```markdown
# Consensus Synthesis Report

## Agreement Summary
| Agent | Confidence | Key Concerns |
|-------|------------|--------------|
| Domain Modeler | X/10 | ... |
| Systems Architect | X/10 | ... |
| Product Designer | X/10 | ... |
| Data Engineer | X/10 | ... |
| Adversarial Reviewer | X/10 | ... |

## Unanimous Agreements
- [Changes all agents support]

## Contested Points
| Point | Positions | Resolution |
|-------|-----------|------------|
| ... | Agent 1: X, Agent 3: Y | [Proposed resolution or "needs iteration"] |

## Final Amended Proposal
[Complete updated tag ontology incorporating all accepted changes]

## Consensus Status
[CONSENSUS REACHED / NEEDS ITERATION]
- If needs iteration, list specific issues to address in round 2
```
</output_format>

<execution_instructions>
1. Deeply consider each agent's unique perspective before writing their report
2. Each agent should build on previous agents' observations
3. Agents should directly respond to questions raised by earlier agents
4. Use extended thinking to thoroughly explore implications
5. Be specific - vague concerns without proposed solutions are not helpful
6. The adversarial reviewer should be genuinely challenging, not rubber-stamping
7. If consensus is not reached after round 1, explicitly state what needs resolution and run a focused round 2
8. The final output should be a complete, implementable tag ontology
</execution_instructions>

<success_criteria>
- All 5 agents have produced substantive reports
- All raised issues have proposed resolutions
- Final proposal has no internal contradictions
- All agents rate final proposal >= 7/10
- The ontology is concrete enough to implement immediately
- The ontology is general enough for non-screenshot domains
</success_criteria>

<verification>
Before declaring consensus:
- Verify no mutually exclusive tags can coexist
- Verify all workflow paths have complete tag coverage
- Verify state can be derived unambiguously from tags
- Verify the proposal addresses all agents' high-severity issues
- Test mentally with 3 different domains (screenshot annotation, document review, data validation)
</verification>
