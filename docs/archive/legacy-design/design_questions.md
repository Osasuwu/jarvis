# Design Questions - Self-Improvement Module

## Implementation Notes

### Design Decisions Implemented

#### Q1: Integration Method (File-Based for MVP)
**Implemented:** File-based Copilot handoff in `copilot_interface.py`
- Agent writes `CopilotPrompt` to `.copilot_queue/{id}.json`
- User manually copies prompt to VS Code Copilot Chat
- Post-MVP: Investigate Chat Participants API for programmatic integration

#### Q2: Approval Workflow Integration
**Implemented:** New `ImprovementApprovalPrompt` class in `safety/confirmation.py`
- Extends existing safety module for consistency
- Structured approval with historical context
- Options: approve/reject/edit/skip_category
- Reuses risk-level infrastructure from safety layer

#### Q3: Edit Loop with Diff
**Implemented:** Single edit loop in `orchestrator._request_approval()`
- User can edit prompt once per opportunity
- Shows unified diff after editing
- Requires re-approval for edited prompts
- Tracks edits with `user_edited=true` flag for learning

#### Q4: Analyzer Error Handling
**Implemented:** Silent logging with continuation in `detector.py`
- Analyzer failures logged at appropriate levels
- Continues with other analyzers on failure
- User can check logs if needed
- Non-critical for agent operation

#### Q5: Cycle-Based Rate Limiting
**Implemented:** Per-cycle tracking in `tracker.py`
- One cycle = one `run_cycle()` execution
- Session concept deferred to future
- Rate limits: 20/week global, 3/file/week, 5/category/cycle

#### Q6: Detector Configuration
**Implemented:** Hardcoded defaults in `detector._register_default_analyzers()`
- MVP scope: PylintAnalyzer and ComplexityAnalyzer
- Post-MVP: Extract to `configs/detectors.yaml`
- Clean abstraction allows easy switch to config-file

#### Q7: Duration Tracking
**Implemented:** Wall-clock time in `ExecutionReport`
- Tracks enqueue-to-decision time (approval latency)
- New fields: `created_at`, `approved_at`, `approval_latency` property
- Indicates prompt clarity (fast approval = clear prompt)
- Manual user time tracking skipped for MVP

#### Q8: Decision-to-Detector Mapping
**Implemented:** Explicit `detector_name` field in `ApprovalDecision`
- Reliable pattern analysis and learning
- Queryable for approval rates per detector
- Accurate cooldown management per detector
- Better audit trail than heuristic matching

---

### Already Implemented (Pre-Questions)
- ✅ File-based Copilot handoff (fallback method)
- ✅ Rate limiting (global, per-file, per-category)
- ✅ Cooldown management (1→3→7 days escalation)
- ✅ Protected path exclusions
- ✅ Pluggable analyzer architecture
- ✅ Detector tracking in approval decisions

### Future Enhancements (Post-MVP)
- Time-based filtering for execution reports
- Real-time best practices research using web_fetch
- VS Code Extension for direct Copilot integration
- Config-file based detector registration
- Session concept for multi-cycle tracking
- Analytics dashboard for approval metrics
