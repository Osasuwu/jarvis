# Phase 7 Critical Fixes Plan

## Scope & Acceptance (Critical)
- Tool auto-discovery (remove hardcoded registrations; configurable sources; dedupe; validation; safe fallback).
- Error handling & resilience (retry/timeout policy for LLM + tools; scoped exceptions; graceful degradation; human-in-the-loop respected).
- Structured logging foundation (structured events, minimal context fields; ready for metrics/tracing later).

### Success Criteria
- Discovery: `main.py` uses discovery pipeline; builtin + optional config/dirs; duplicate names rejected with clear errors; no regressions loading existing builtin tools.
- Resilience: LLM/tool execution wrapped with retry/timeout policy; specific exceptions; orchestrator loop degrades gracefully; safety hooks remain in place.
- Logging: Structured logger available; key events emit `component`, `action`, `status`, `duration_ms`, `request_id` (when available); easy to extend with metrics/tracing.
- Tests: New unit tests for discovery, retries/timeouts, and logging surface; integration test for orchestrator with discovered tools; existing tests kept green.

## Design Notes (Draft, no implementation yet)

### Tool Discovery
- Modules: `tools/discovery.py` (orchestration), `tools/loader.py` (dynamic load helpers), optional `configs/tools.yaml` for config-driven sources.
- Sources: builtin registry, directory scan (Python modules), config-driven specs. Order: builtin → config → directories. Deduplicate by tool name; log and skip conflicts with explicit error.
- Validation: basic schema for tool spec (name, module, class, enabled); failure should not crash agent—fallback to builtin.
- Safety: discovery is read-only; execution still gated by safety layer.

### Resilience/Error Handling
- Modules: `core/exceptions.py` (domain-specific errors), `core/resilience.py` (retry/timeout helpers; policies for LLM and tools).
- Policies: exponential backoff with cap; classify retryable errors (network/timeouts) vs non-retryable (validation). Timeouts per tool and per LLM call.
- Orchestrator: wrap planner/LLM and executor calls; on persistent failure, surface clear user message + gap detection suggestion; keep memory consistent.

### Logging/Observability
- Module: `observability/logging.py` to provide `get_logger`/`setup_logging` using structured logging (keep stdlib for now; ready for structlog). Common fields: component, action, status, duration_ms, request_id, tool_name.
- Hooks: orchestrator steps (plan, execute, observe), tool execution start/stop, retries, timeouts. Metrics/tracing stubs can be added later.

## Testing Strategy (outline)
- Unit: discovery (builtin load, config load, dir load, dedupe conflicts, invalid spec fails gracefully); resilience (retry only on retryable errors, timeout raises proper exception); logging (logger emits expected fields).
- Integration: orchestrator with discovered tools; simulate tool failure to verify gap detection path still works; ensure retries/timeouts not breaking loop.
- Regression: CLI chat path still loads builtin tools; no change in default behavior when optional configs are absent.

## Execution Plan
- Step 1: Land skeleton modules with TODOs and docstrings (no behavior change).
- Step 2: Implement tool discovery + tests; wire `main.py` to use it.
- Step 3: Implement resilience layer + orchestrator integration + tests.
- Step 4: Add structured logging foundation + integration points + tests.
- Step 5: Run full test suite; prepare PR → merge into `main`.
