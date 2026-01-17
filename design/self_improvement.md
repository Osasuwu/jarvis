## 1. Problem Statement

The agent needs a supervised self-improvement capability where it can propose and implement changes to its own codebase. To minimize implementation burden on the human and maximize safety, the agent will:

1. Analyze its own workspace to identify gaps, bugs, or improvement opportunities
2. Generate targeted prompts for VS Code Copilot Chat to implement changes
3. Submit each prompt to human for approval before execution
4. Track approved/rejected prompts to learn what changes are acceptable

**Key Design Constraints:**
- All workspace modifications must go through VS Code Copilot Agents (not direct file edits)
- Every prompt requires explicit human approval (safety gate)
- Agent focuses on "what to improve and how to ask Copilot" - not on writing the code itself
- Human role shifts from implementer to reviewer/approver

**Success Criteria:**
- Agent can identify meaningful improvement opportunities in its own code
- Generated prompts are clear, contextual, and atomic enough for Copilot to handle
- Approval workflow is low-friction (not overwhelming the human with micro-requests)
- System maintains a learning loop based on approval/rejection patterns

## 2. Architectural Placement

### Component Location
This feature is architecturally parallel to the **Capability Gap Analyzer** but operates at a meta-level on the codebase itself rather than on runtime capabilities.

**New Top-Level Module:** `src/jarvis/self_improvement/`

```
src/jarvis/
├── core/           # Existing orchestrator, planner, executor
├── gap_analyzer/   # Existing capability gap detection
├── self_improvement/  # NEW: Codebase improvement system
│   ├── detector.py        # Analyzes workspace for improvement opportunities
│   ├── proposer.py        # Generates Copilot prompts for improvements
│   ├── researcher.py      # Researches best practices, patterns (optional)
│   ├── tracker.py         # Tracks approval/rejection history
│   └── copilot_interface.py  # VS Code Copilot Chat integration
├── tools/
├── safety/         # Reuses existing Human-in-the-Loop mechanisms
└── ...
```

### Component Boundaries & Responsibilities

#### 1. **Detector** (`detector.py`)
**Responsibility:** Identify improvement opportunities in the workspace
- **Input:** Workspace path, analysis scope (optional filters)
- **Output:** List of `ImprovementOpportunity` objects
- **Capabilities:**
  - Static code analysis (linting, complexity metrics)
  - Test coverage gaps detection
  - Documentation completeness checks
  - Anti-pattern detection
  - Dependency/security audit results

**Contract:**
```python
class ImprovementOpportunity:
    category: str  # "bug", "refactor", "test", "docs", "security"
    severity: str  # "critical", "high", "medium", "low"
    location: FileLocation  # file path + line range
    description: str
    context: dict  # surrounding code, metrics, etc.
```

#### 2. **Proposer** (`proposer.py`)
**Responsibility:** Generate Copilot prompts for approved opportunities
- **Input:** `ImprovementOpportunity`, codebase context
- **Output:** `CopilotPrompt` ready for human review
- **Capabilities:**
  - Context extraction (relevant files, dependencies)
  - Prompt templating with best practices
  - Scope validation (atomic, testable changes)
  - Quality heuristics (clarity, specificity)

**Contract:**
```python
class CopilotPrompt:
    id: str  # unique identifier
    opportunity_ref: str
    prompt_text: str  # the actual prompt for Copilot
    context_files: list[str]  # files Copilot should consider
    expected_changes: list[str]  # predicted file modifications
    priority: int
```

#### 3. **Tracker** (`tracker.py`)
**Responsibility:** Maintain history of proposals and learn from patterns
- **Input:** Prompt approvals/rejections with optional feedback
- **Output:** Historical analytics, rejection patterns
- **Storage:** Local file (JSON/SQLite), no external dependencies
- **Capabilities:**
  - Record approval decisions with timestamps
  - Pattern analysis (which categories get approved?)
  - Rate limiting (prevent spam)
  - Suggest priority adjustments based on history

#### 4. **CopilotInterface** (`copilot_interface.py`)
**Responsibility:** Bridge between agent and VS Code Copilot Chat
- **Input:** Approved `CopilotPrompt`
- **Output:** Execution status, Copilot response (if available)
- **Integration Options:**
  - **Option A:** VS Code API via extension (requires VS Code extension development)
  - **Option B:** File-based handoff (agent writes prompt to `.copilot_queue/`, user copies to chat)
  - **Option C:** Chat participants API (if available in VS Code)

**Note:** Implementation details depend on VS Code extensibility capabilities investigation.

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    User triggers improvement cycle           │
│                 (CLI command or periodic schedule)           │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    Detector     │
                    │  (Analyze code) │
                    └────────┬────────┘
                             │ List<ImprovementOpportunity>
                             ▼
                    ┌─────────────────┐
                    │ Priority Filter │ (top N by severity/history)
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    Proposer     │
                    │ (Generate prompt)│
                    └────────┬────────┘
                             │ CopilotPrompt
                             ▼
            ┌────────────────────────────────┐
            │   Safety Layer (Existing)      │
            │   Human Approval Request       │
            │   - Show opportunity context   │
            │   - Show generated prompt      │
            │   - Approve / Reject / Edit    │
            └───────────┬──────────┬─────────┘
                        │          │
              Approved  │          │ Rejected
                        ▼          ▼
            ┌──────────────┐  ┌──────────┐
            │   Tracker    │  │ Tracker  │
            │ (log accept) │  │(log deny)│
            └──────┬───────┘  └──────────┘
                   │
                   ▼
          ┌─────────────────────┐
          │ CopilotInterface    │
          │ (Execute via Copilot)│
          └──────────┬──────────┘
                     │ Result / Error
                     ▼
          ┌─────────────────────┐
          │   Verify Changes    │ (Optional: run tests, lints)
          │   Report to user    │
          └─────────────────────┘
```

### Integration Points

#### Reuse Existing Systems
1. **Safety Layer (`src/jarvis/safety/`):** 
   - Reuse `confirmation.py` for approval UI
   - Extend `RiskLevel` enum if needed (e.g., `CODEBASE_MODIFICATION`)

2. **Orchestrator (`src/jarvis/core/`):**
   - Integrate as a special "meta-task" type
   - Can be triggered manually or scheduled

3. **Memory (`src/jarvis/memory/`):**
   - Store improvement history in conversation context
   - Track long-term improvement trends

#### New External Dependencies
- Static analysis tools (e.g., `pylint`, `radon`, `bandit`)
- VS Code extension APIs (investigation required)

### Extension Points

1. **Pluggable Detectors:** Other engineers can add domain-specific analyzers (e.g., performance, accessibility)
2. **Custom Prompt Templates:** Per-category prompt strategies can be configured
3. **Post-Execution Hooks:** Validation steps after Copilot changes (e.g., CI checks)
4. **Learning Adapters:** Different ML approaches for pattern recognition from approval history

### Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **VS Code API limitations** | Cannot integrate Copilot programmatically | Fallback to file-based handoff (manual copy-paste) |
| **Prompt quality** | Copilot produces incorrect changes | Multi-stage approval: prompt approval + change review |
| **Analysis false positives** | Too many low-value suggestions | Tunable thresholds, learning from rejections |
| **Meta-recursion** | Agent modifies self-improvement logic unsafely | Explicit scope exclusion for `self_improvement/` module |
| **Approval fatigue** | User overwhelmed by requests | Batching related changes, priority filtering, rate limits |
| **Code churn** | Repeated changes to same area | Cooldown periods per file/function, track edit frequency |

### Non-Goals (Out of Scope)
- Direct file editing by agent (must go through Copilot)
- Fully autonomous improvements (always requires human approval)
- Production deployment automation (stays in development environment)
- Complex refactorings requiring architectural changes (human-driven only)

## 3. Agent Reasoning Model
**Phase 0 — Entry Guard**
- Validate trigger type (manual run, scheduled run) and confirm scope excludes protected paths (`self_improvement/`, safety modules). If violation, halt and request human decision.
- Check rate limits and cooldowns (per file/module and global). If exceeded, defer and log reason.

**Phase 1 — Detection Plan Selection**
- Choose detectors based on configured categories, recent rejection patterns, and risk level. Skip detectors whose last run produced only rejected items unless cooldown expired.
- Stop if no detectors are eligible or workspace state is unreadable; escalate with a minimal incident note.

**Phase 2 — Opportunity Vetting**
- Deduplicate and merge overlapping findings; discard items lacking precise file+line ranges or actionable descriptions.
- Score each `ImprovementOpportunity` using severity (critical>high>medium>low), confidence (detector-specific), impact surface (files touched, test coverage), and historical approval rate for that category.
- Select top N within limits; if zero remain, end cycle quietly.

**Phase 3 — Proposal Synthesis**
- For each selected opportunity, assemble an action spec: objective, minimal scope (files/lines), expected change types, and required context files. Reject opportunities that are not atomic (e.g., span unrelated modules) or whose expected outcome cannot be stated clearly.
- If context exceeds size thresholds, split into smaller, independent specs or defer with a note.

**Phase 4 — Approval Packaging**
- Batch specs by file or category when doing so preserves atomicity; otherwise keep singletons. Enforce a per-cycle max batch to avoid approval fatigue.
- Attach risk level and validation plan (tests/linters to run after Copilot changes). If risk exceeds configured ceiling, require explicit “high-risk” confirmation.

**Phase 5 — Execution Gate**
- Before sending to Copilot interface, re-check workspace cleanliness (no untracked critical files, no unresolved conflicts). If dirty in unrelated areas, proceed but highlight affected files; if conflicts exist, stop and escalate.
- If human approves: enqueue to CopilotInterface with the packaged context. If human edits or rejects: record feedback and either re-scope (if edit) or cool down (if reject).

**Phase 6 — Post-Execution Verification**
- After Copilot response, verify expected files changed and validations planned in Phase 4. If validations fail or changes diverge from expected scope, roll back the proposal state, flag as “failed execution,” and surface to human for decision.
- If results match expectations and validations pass, mark as complete and ready for optional commit workflow (outside this module).

**Phase 7 — Learning Update**
- Log outcomes (approved, rejected, failed execution, success) with category, detector, and reason codes.
- Adjust detector weights and rate limits using recent approval/rejection ratios; increase cooldowns for repeatedly rejected categories or files.
- Persist a concise audit trail for every stop, defer, and escalation event.

**Stop Conditions and Escalations**
- Stop immediately on scope violations, missing line-level context, workspace conflicts, or exceeded risk threshold without explicit override.
- Escalate to human with a short incident note when detectors are ineligible, validations fail, Copilot changes are off-scope, or required confirmations are absent.
- Quietly terminate cycle when no eligible opportunities remain after vetting and scoring.

## 4. Prompt Constraints

### Behavioral Rules (DO)

**Opportunity Detection & Vetting**
- DO analyze workspace only within configured scope (exclude `self_improvement/`, `safety/`, test fixtures by default)
- DO attach precise file+line ranges to every opportunity (no vague "somewhere in module X")
- DO assign severity levels from enum: `{CRITICAL, HIGH, MEDIUM, LOW}`
- DO assign confidence scores (0.0–1.0) based on detector certainty
- DO deduplicate overlapping findings before vetting
- DO discard opportunities lacking actionable descriptions (must start with imperative verb)
- DO validate atomicity: each opportunity must affect ≤3 related files or be self-contained to one function/class
- DO include risk assessment: mark opportunities requiring `HIGH_RISK_APPROVAL` if they modify core modules, remove functionality, or affect 5+ files

**Proposal Generation**
- DO generate one `CopilotPrompt` per approved `ImprovementOpportunity`
- DO include immediate context: show affected code snippet (20–50 lines max) in prompt preamble
- DO state expected changes explicitly (e.g., "Will add type hints to function X and update docstring")
- DO reference file paths and line numbers consistently (absolute paths from workspace root)
- DO validate prompt length <2000 tokens; split opportunities exceeding this limit
- DO include validation plan: specify which tests/linters must pass post-execution
- DO mark required context files: list all files Copilot must consider (max 10 files)
- DO assign unique immutable IDs to prompts (format: `SI_<category>_<timestamp>_<hash>`)

**Batch Packaging**
- DO group related opportunities by category or file when atomicity is preserved
- DO enforce per-cycle batch limit: max 5 independent prompts per approval cycle
- DO preserve order: prioritize by severity (CRITICAL → HIGH → MEDIUM → LOW)
- DO include clear separation headers between batched prompts
- DO attach risk summary: list all `HIGH_RISK_APPROVAL` items upfront

**Approval Requests**
- DO present structured approval packets with these fields:
  ```json
  {
    "id": "SI_<category>_<timestamp>_<hash>",
    "opportunity": {...},
    "prompt": "...",
    "expected_impact": ["file1.py", "file2.py"],
    "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
    "validation_plan": ["pytest module/tests/...", "pylint --disable=..."],
    "requires_high_risk_approval": boolean,
    "estimated_effort": "1-5 minutes"
  }
  ```
- DO flag high-risk changes with prominent `⚠️ HIGH RISK` indicators
- DO show approval options: `[APPROVE]`, `[REJECT]`, `[EDIT]`, `[DEFER]`
- DO include historical context: show approval/rejection rate for this category (e.g., "Similar improvements: 3 approved, 1 rejected")

**Execution & Reporting**
- DO record every approval/rejection decision with exact timestamp and reason code
- DO report execution results in structured format:
  ```json
  {
    "prompt_id": "SI_...",
    "status": "SUCCESS|FAILED|PARTIAL",
    "files_modified": ["file1.py"],
    "validation_results": {"pytest": "PASS", "pylint": "PASS"},
    "duration_seconds": 45,
    "copilot_response_summary": "...",
    "notes": "..."
  }
  ```
- DO verify expected files changed and modifications align with scope
- DO surface failures explicitly (e.g., "Copilot modified test_xyz.py but should only modify xyz.py")

**Rate Limiting & Cooldowns**
- DO check and enforce rate limits before processing:
  - Global: max 20 improvements per week
  - Per-file: max 3 improvements per 7 days
  - Per-category: max 5 per cycle
- DO apply increasing cooldowns on repeated rejections (1 day → 3 days → 7 days)
- DO skip detectors if their last 5 suggestions were all rejected (reset after 7 days)

---

### Forbidden Behaviors (DO NOT)

**Scope & Safety Violations**
- DO NOT generate opportunities targeting `self_improvement/`, `safety/`, or `core/orchestrator.py` modules
- DO NOT create recursive self-modifications (agent modifying proposal generation logic)
- DO NOT bypass approval workflow or submit unapproved prompts to Copilot
- DO NOT process workspace if unresolved Git conflicts exist (check `git status` first)
- DO NOT proceed if workspace is dirty in protected modules without explicit human flag
- DO NOT exceed configured risk threshold (`HIGH_RISK_APPROVAL` ceiling) without manual override

**Opportunity Quality**
- DO NOT generate opportunities without precise line numbers (ranges like "lines 10–25" required)
- DO NOT create opportunities spanning unrelated concerns (e.g., "fix linting AND add feature")
- DO NOT emit vague descriptions ("improve this code" → FORBIDDEN; "add missing type hints to get_user()" → OK)
- DO NOT deduplicate by losing specificity (merge only if line ranges overlap >80%)
- DO NOT include opportunities with confidence <0.5 unless severity is CRITICAL

**Prompt Generation**
- DO NOT generate prompts >2000 tokens; defer oversized opportunities
- DO NOT omit context files required to understand the change
- DO NOT reference internal IDs or UUIDs in user-facing prompt text
- DO NOT assume Copilot has domain context; always include "why" (e.g., "for consistency with module X")
- DO NOT submit prompts without validation plan attached
- DO NOT create dependent opportunities that require sequential approval (one change must not block another)

**Approval & Execution**
- DO NOT auto-approve any opportunity; require explicit human decision
- DO NOT modify approval request after human has reviewed (if content changed, require re-approval)
- DO NOT execute partial batches (all-or-nothing within a batch)
- DO NOT suppress errors; surface every validation failure to human with full context
- DO NOT commit changes automatically; leave workspace dirty for user review

**Data & Audit**
- DO NOT lose approval history or decision reasons (maintain immutable audit log)
- DO NOT reset rate limits or cooldowns without explicit admin action
- DO NOT delete or modify past improvement records (only append)
- DO NOT share approval patterns with external systems without consent

---

### Output Formats (Required)

**ImprovementOpportunity (Input Contract)**
```json
{
  "id": "string (unique, immutable)",
  "detector": "string (e.g., 'pylint', 'test_coverage', 'complexity')",
  "category": "string (enum: bug|refactor|test|docs|security|performance)",
  "severity": "string (enum: CRITICAL|HIGH|MEDIUM|LOW)",
  "confidence": "number (0.0–1.0)",
  "file": "string (absolute path from workspace root)",
  "line_range": {
    "start": "integer (1-indexed)",
    "end": "integer (1-indexed)"
  },
  "description": "string (imperative, <200 chars)",
  "context": {
    "code_snippet": "string (20–50 lines)",
    "affected_files": ["string"],
    "metrics": {"object": "any"}
  },
  "atomic": "boolean (true if change is self-contained)",
  "estimated_effort": "string (enum: trivial|small|medium|large)"
}
```

**CopilotPrompt (Output Contract)**
```json
{
  "id": "string (SI_<category>_<timestamp>_<hash>)",
  "opportunity_id": "string (reference)",
  "prompt_text": "string (max 2000 tokens)",
  "context_files": ["string (1–10 files)"],
  "expected_changes": [
    {
      "file": "string",
      "change_type": "enum: ADD|MODIFY|REMOVE",
      "description": "string"
    }
  ],
  "validation_plan": [
    "string (e.g., 'pytest src/module/tests', 'pylint --disable=...')"
  ],
  "risk_level": "enum: LOW|MEDIUM|HIGH|CRITICAL",
  "requires_high_risk_approval": "boolean",
  "priority": "integer (1–10, higher = more urgent)",
  "generated_at": "ISO 8601 timestamp"
}
```

**ApprovalRequest (User-Facing)**
```
┌─────────────────────────────────────────────────────┐
│ IMPROVEMENT PROMPT #SI_<id>                         │
├─────────────────────────────────────────────────────┤
│ Category: <category>  Severity: <severity>          │
│ Risk Level: ⚠️ <risk_level>                         │
│ File: <file>:<line_range>                           │
├─────────────────────────────────────────────────────┤
│ Opportunity:                                        │
│ <description>                                       │
│                                                     │
│ Context Snippet:                                    │
│ <code_snippet (50 lines max)>                       │
├─────────────────────────────────────────────────────┤
│ Copilot Prompt:                                     │
│ <prompt_text>                                       │
│                                                     │
│ Expected Changes:                                   │
│ - <file>: <change_type> (<description>)            │
│                                                     │
│ Validation Plan:                                    │
│ - pytest ...                                        │
│ - pylint ...                                        │
│                                                     │
│ Historical Context:                                 │
│ Similar improvements: 5 approved, 2 rejected       │
│ (Approval rate: 71%)                               │
├─────────────────────────────────────────────────────┤
│ [APPROVE] [EDIT] [REJECT] [DEFER]                  │
└─────────────────────────────────────────────────────┘
```

**ExecutionReport (Output)**
```json
{
  "prompt_id": "string",
  "status": "enum: SUCCESS|FAILED|PARTIAL|ROLLBACK",
  "files_modified": ["string"],
  "files_expected": ["string"],
  "scope_match": "boolean (expected_changes aligned with actual)",
  "validations": {
    "pytest": {
      "status": "enum: PASS|FAIL|SKIPPED",
      "output": "string (first 500 chars)"
    },
    "pylint": {
      "status": "enum: PASS|FAIL|SKIPPED",
      "output": "string"
    }
  },
  "duration_seconds": "integer",
  "error_details": "string (if status != SUCCESS)",
  "copilot_response_length": "integer",
  "user_notes": "string (from approval)"
}
```

---

### Explanation

These constraints ensure:
- **Controllability:** Every step has explicit approval gates and forbidden boundaries
- **Traceability:** Audit logs and structured formats enable debugging and learning
- **Safety:** Scope exclusions, risk checks, and validation gates prevent harmful modifications
- **Stability:** Immutable IDs, versioned schemas, and atomic changes enable reliable reruns
- **Clarity:** Structured requests and reports reduce ambiguity in human-agent communication

## 5. Code Rewiew
(owned by Code Rewiewer)

## 6. Backend Contract
(inputs, outputs, data models)

## 7. Open Questions / TODO

### Critical Path (Must Resolve Before Implementation)

**CP-1: VS Code Copilot Integration Method**
- **Question:** What is the technical mechanism to invoke Copilot Chat from external code?
- **Options:** 
  - VS Code Extension API (requires extension development)
  - Chat Participants API (if publicly available)
  - File-based queue with manual trigger (fallback)
- **Owner:** Backend Engineer + VS Code API research
- **Priority:** CRITICAL - determines entire interface architecture
- **Action:** Spike to investigate VS Code extensibility APIs

**CP-2: Approval UI/UX Pattern**
- **Question:** How does user approve/reject prompts in practice?
- **Options:**
  - Inline CLI prompt (blocking)
  - Async queue with separate review command
  - Web dashboard (requires web UI)
  - VS Code notification with actions
- **Owner:** UI/UX + Implementation team
- **Priority:** HIGH - affects user experience flow
- **Dependency:** Requires existing safety layer review

**CP-3: Scope Control Mechanism**
- **Question:** How to prevent meta-recursion and unsafe self-modifications?
- **Options:**
  - Hard-coded exclusion list (`self_improvement/` always excluded)
  - Configuration-based scope rules
  - Runtime permission checks
- **Owner:** Safety Engineer
- **Priority:** HIGH - safety-critical feature
- **Decision Criteria:** Must be tamper-proof, cannot be bypassed by agent

### Design Decisions Needed

**D-1: Detector Implementation Strategy**
- Which static analysis tools to integrate? (pylint, mypy, radon, bandit, custom?)
- Run all tools or selective based on improvement category?
- Performance considerations: analyze on-demand vs. continuous background?

**D-2: Prompt Template Strategy**
- Fully generated prompts vs. template-based with placeholders?
- Should prompts include code snippets or just descriptions?
- Maximum prompt length constraints?

**D-3: Learning Approach**
- Simple pattern matching on approval history?
- ML-based scoring (requires training data)?
- Rule-based heuristics?
- Start simple, evolve later?

**D-4: Batching Strategy**
- Group related improvements (e.g., all tests for one module)?
- Present top N individually or all at once?
- Allow user to reorder/reprioritize batch?

### Integration Details

**I-1: Git Workflow**
- Should agent create feature branches automatically?
- Commit granularity: per improvement or batched?
- Automatic commit messages: agent-generated or user-provided?

**I-2: Validation Pipeline**
- Which validations run after Copilot changes? (tests, linters, type checks?)
- Blocking vs. warning validations?
- Rollback automation if validation fails?

**I-3: Storage Format**
- Where to persist approval history? (JSON file, SQLite, in-memory?)
- Schema for `ImprovementOpportunity` and `CopilotPrompt`?
- Rotation policy for old records?

### Feature Scoping

**S-1: MVP Scope**
- Which improvement categories in MVP? (suggest: linting errors, test coverage gaps only)
- Exclude complex refactorings initially?
- Manual trigger only or also scheduled?

**S-2: Prompt Quality Gates**
- Pre-approval validation rules for generated prompts?
- Human editing of prompts before sending to Copilot?
- A/B testing different prompt formulations?

**S-3: Rate Limiting**
- Max improvements per session/day?
- Cooldown period per file/module?
- Throttling strategy when rejection rate is high?

### Research Needed

**R-1: VS Code Copilot Chat API**
- **Task:** Investigate programmatic access to Copilot Chat
- **Deliverable:** Feasibility report with code samples
- **Timeline:** Before detailed design

**R-2: Static Analysis Tool Comparison**
- **Task:** Evaluate integration complexity of various Python linters/analyzers
- **Deliverable:** Recommendation matrix (tool vs. feature vs. performance)
- **Timeline:** During implementation planning

**R-3: Approval Pattern Analysis**
- **Task:** Survey similar approval workflows in other tools (GitHub Actions, CI/CD)
- **Deliverable:** UX patterns document
- **Timeline:** Before UI implementation

### Risks Requiring Monitoring

**M-1: Approval Fatigue**
- **Metric:** Track approval vs. rejection ratio over time
- **Threshold:** If >70% rejections, reduce suggestion frequency
- **Mitigation:** Implement learning to filter low-value suggestions

**M-2: Prompt Quality Drift**
- **Metric:** Track Copilot execution success rate
- **Threshold:** If <50% success, review prompt generation logic
- **Mitigation:** Maintain prompt quality benchmark suite

**M-3: Code Churn**
- **Metric:** Track files modified repeatedly by self-improvement
- **Threshold:** If same file modified >3 times in 7 days, flag for review
- **Mitigation:** Implement per-file cooldown periods

### Future Enhancements (Post-MVP)

- **Multi-agent collaboration:** Different specialized agents for different improvement types
- **Community prompt library:** Share successful prompts across users
- **Regression detection:** Monitor if improvements degrade performance/functionality
- **Continuous improvement mode:** Background analysis with batched weekly reviews