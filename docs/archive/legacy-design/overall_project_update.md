## 1. Problem Statement
We need to assess the current state of the project (architecture, agent behavior, prompts, and codebase)
to identify risks, technical debt, and blockers before implementing new features.

## 2. Current Architecture Assessment
(owned by Architect)

### Current Structure
A layered ReAct agent with plugin-based tool system:
- **Core orchestration**: Orchestrator → Planner → Executor → ToolRegistry
- **LLM abstraction**: Provider interface with Groq/Ollama implementations
- **Plugin system**: Tool base class + Registry + Discovery + Loader
- **Safety layer**: SafeExecutor, ConfirmationPrompt, AuditLogger, WhitelistManager
- **Supporting modules**: Memory (conversation), GapAnalyzer (detector/researcher/proposer), Observability (logging)
- **Entry point**: CLI via Typer + Rich

Component initialization is centralized in `main.py::_create_orchestrator()`.

### Major Architectural Issues

**1. Tight coupling between core components**
- Orchestrator directly instantiates Planner, Executor, and 3 GapAnalyzer components
- No dependency injection; hard to test, swap implementations, or mock
- Orchestrator has 5+ direct dependencies creating brittle composition

**2. Safety layer is disconnected**
- SafeExecutor exists in `safety/` but is NOT integrated into Orchestrator or Executor
- Human approval logic scattered: confirmation prompt unused in tool execution flow
- Risk assessment happens at tool level but not enforced at execution time
- Audit logging present but not wired into actual tool calls

**3. Configuration complexity**
- Config uses Pydantic Settings with multiple nested classes (LLM, Tools, Memory, Agent, Logging)
- Environment variable handling duplicated: `get_config()` + manual `os.getenv()` in main.py
- No validation of config consistency (e.g., missing API key with selected provider)

**4. Implicit orchestration flow**
- ReAct loop in Orchestrator is 260+ lines, single method
- State machine implicit: iteration counter, flags like `tool_called_once`
- No clear boundaries between "think", "act", "observe" phases
- Error handling mixed with business logic

**5. Tool discovery fragility**
- Discovery scans file system, imports, introspects classes at runtime
- Builtin tools hardcoded in `discovery.py` import statement
- No versioning, capability conflict detection, or dependency management
- Loader/Discovery/Registry responsibilities overlap

**6. LLM provider abstraction leaks**
- GroqProvider uses OpenAI API format but abstracts it poorly
- LocalStubProvider has different behavior (no actual model calls)
- Tool schema format tied to OpenAI function calling format
- No provider capability negotiation (some may not support tools)

**7. Memory has no persistence layer implemented**
- `MemorySettings.persist_to_disk=True` but ConversationMemory only holds in-memory list
- No serialization, no storage backend connected
- No conversation ID or session management

### Architectural Risks

**Scalability blockers:**
- Synchronous discovery of tools (file I/O) on every agent startup
- No lazy loading or caching of tool metadata
- Conversation memory unbounded (max_length checked but not enforced)
- No async batching or parallel tool execution despite `max_parallel_executions` config

**Maintainability hazards:**
- Circular import potential: many modules import from `jarvis.X` without interface contracts
- Core logic (Orchestrator) mixes concerns: memory, LLM, planning, execution, gap analysis
- Testing requires full system initialization (Orchestrator needs LLM + Registry + Memory)
- No clear extension points: adding new provider/tool type requires modifying discovery

**Missing contracts:**
- Tool interface has `execute()` but no lifecycle hooks (init/cleanup/validate)
- No protocol for tool dependencies or inter-tool communication
- LLMProvider interface lacks streaming, embeddings, or token counting
- No versioned API boundaries between components

**Observability gaps:**
- `set_request_id()` called but not propagated through execution chain
- Logging scattered (logger instances per module) without correlation
- No metrics, no performance tracking
- Error recovery logic opaque (RetryPolicy in resilience.py exists but unclear where applied)

**Human-in-loop not enforced:**
- Risk levels defined (Tool.risk_level) but SafeExecutor is bypassed
- No centralized approval mechanism in execution path
- AuditLogger created but not used during tool execution
- Whitelist manager exists but not checked

## 3. Current Agent Behavior Assessment

### Goal Interpretation
**Raw pass-through with no decomposition:**
- User input is added directly to memory with no parsing, extraction, or normalization
- No explicit goal structure (e.g., primary/subgoals, success criteria, constraints)
- LLM sees raw user text + conversation history → infers intent implicitly
- For local LLM fallback: simple keyword heuristics (e.g., "список" → list_directory)
- **Risk:** Ambiguous/contradictory requests treated identically; no fallback for unclear goals

### Decision Making Flow
**Entirely delegated to LLM via function calling:**
1. Orchestrator gathers conversation history
2. Passes messages + tool schemas to LLM via `complete()`
3. LLM returns: text content + optional tool_calls
4. Orchestrator checks: if tool_calls exist → ACT; else → RESPOND
5. No intermediate reasoning layer, planner, or feasibility check

**Implicit state machine:**
- `tool_called_once` flag gates tool availability (tools only provided on first iteration, then None on subsequent calls)
- Iteration counter prevents infinite loops
- No explicit stop conditions; exits when: (a) LLM returns no tool_calls, (b) max_iterations reached, or (c) unrecoverable error

### Tool Selection Mechanism
**No explicit selection; LLM chooses freely:**
- Tool schemas provided as OpenAI function calling format to LLM
- LLM generates: tool_name + arguments dict
- Executor validates: tool exists + parameters valid (via JSON schema)
- If invalid: error logged, tool result marked failed, added to memory, loop continues
- **No capability negotiation:** tool_called_once=True after first call → tools hidden from future LLM prompts (logic unclear on intent)

### Failure & Uncertainty Handling

**Failures are caught at execution level:**
- Tool validation failures: caught in executor, added to memory as "tool result"
- Tool execution exceptions: wrapped in try/catch, logged, added to memory
- LLM call failures: caught, retry attempted (max 2 attempts), generic error returned if both fail

**Gap analysis triggered on tool failure:**
- When tool fails: gap_detector identifies "missing capability"
- gap_researcher researches solution (method unclear/not fully implemented)
- tool_proposer suggests alternative tool (with implementation hints)
- Suggestions added to memory as final response (loop breaks)

**No explicit uncertainty handling:**
- No confidence scores on tool selection
- No validation of tool outputs before using them
- No mechanism to ask for clarification or confirmation (SafeExecutor disconnected)
- LLM error messages re-used as-is without context enrichment

### Unresolved/Missing Logic

**Stop conditions are implicit, not explicit:**
1. LLM returns no tool_calls → assume task complete
2. Max iterations reached → generic "break down your request" message
3. Tool execution fails + gap analysis runs → response constructed and loop breaks
4. No early exit for: "I cannot do this", "this is unsafe", "I need user input"

**Planner exists but is unused:**
- Planner class defined with plan() method but never called during run()
- planner.validate_tool_selection() exists but not invoked
- Task complexity estimation in planner not used for anything

**Memory truncation unpredictable:**
- ConversationMemory uses deque with max_length
- Warns at 90% but does not prevent truncation
- LLM sees potentially incomplete context if memory is truncated mid-conversation

**Tools provided inconsistently:**
- First iteration: tools included in llm_tools
- After first tool call: llm_tools = None (intentionally)
- Logic comment missing; unclear if this is "force LLM to summarize" or bug

---

## 4. Prompt & Instruction Assessment
(owned by Prompt Engineer)

### Prompt Location & Organization

**No centralized prompt management:**
- **LocalStubProvider** contains hardcoded Russian prompt at [llm/local.py](llm/local.py#L224-L244):
  - System prompt built dynamically from tool descriptions
  - Instructions embedded: `"Ты помощник на локальном компьютере..."`, `"Используй формат: <function=tool_name(parameters)></function>"`
  - Tool format specification hardcoded: `"Параметры передавай в виде JSON объекта"`
  - No English/multi-language support
- **GroqProvider** has NO system prompt:
  - Relies entirely on raw conversation messages passed through
  - No role definition, no task framing, no output format constraints
  - Assumes OpenAI function calling format implicitly
- **Orchestrator** has hardcoded fallback messages:
  - Russian error messages: `"Не удалось полностью выполнить запрос..."` [orchestrator.py](orchestrator.py#L192-L207)
  - English timeout message: `"I couldn't complete the task..."` [orchestrator.py](orchestrator.py#L219-L222)
  - No separation between agent logic and user-facing text

**No separation of concerns:**
- System prompts, role definitions, and task instructions are NOT separated
- Tool descriptions serve dual purpose: (1) LLM instruction, (2) registry metadata
- Error messages mixed with code logic (no prompt templates)
- Language switching logic absent (Russian/English mixed inconsistently)

### Consistency & Stability Issues

**Critical inconsistencies:**

1. **Language mixing:**
   - LocalStubProvider uses Russian prompts
   - GroqProvider receives raw English/Russian messages from user
   - Orchestrator error responses switch between Russian/English unpredictably
   - Tool descriptions in English, but LocalStub system prompt in Russian
   - **Risk:** Model confusion, degraded reasoning in multi-turn conversations

2. **No prompt versioning or isolation:**
   - Prompt strings scattered across 3 files: `local.py`, `orchestrator.py`, `main.py`
   - No single source of truth for agent instructions
   - Changes require modifying multiple files
   - **Risk:** Drift between providers, inconsistent agent behavior

3. **Tool schema format leakage:**
   - Tool descriptions written for OpenAI function calling format [base.py](base.py#L77-L103)
   - LocalStubProvider expects different format: `<function=name(params)></function>`
   - GroqProvider assumes JSON tool_calls but no explicit instruction in prompt
   - **Risk:** Provider-specific failures, format mismatches

4. **Implicit context assumptions:**
   - No explicit instruction on when to use tools vs. respond directly
   - No stop condition guidance ("say 'I cannot do this' when...")
   - No output format specification (structured vs. freeform)
   - **Risk:** Hallucinated tool calls, premature/delayed responses

### Missing Constraints & Instructions

**Critical gaps:**

**1. No agent role definition:**
- GroqProvider has zero system prompt → LLM has no identity, capabilities, or boundaries
- LocalStubProvider defines role as `"Ты помощник на локальном компьютере"` but no capabilities/limitations stated
- No explicit instruction on: (a) what agent CAN do, (b) what it CANNOT do, (c) when to ask for clarification

**2. No tool usage guidelines:**
- No instruction on tool selection priorities (when multiple tools could apply)
- No guidance on tool chaining or multi-step execution
- No explicit "use tool X for task Y" mappings
- Tool descriptions are brief (1 sentence) with no usage examples
- **Risk:** LLM guesses tool intent, misuses parameters, ignores better alternatives

**3. No output format specification:**
- No instruction on response structure (markdown, plain text, JSON)
- No guidance on how to present tool results to user
- No template for error explanations
- **Risk:** Inconsistent UX, unparseable outputs, verbose/terse responses

**4. No safety/risk instructions:**
- `risk_level` defined on tools (LOW/MEDIUM/HIGH) but NOT communicated to LLM
- No prompt instruction: "confirm before executing HIGH risk tools"
- No guidance on handling sensitive data or destructive operations
- **Risk:** Agent executes risky operations without understanding implications

**5. No uncertainty handling:**
- No instruction to express confidence levels
- No guidance on when to ask clarifying questions
- No fallback strategy instruction (e.g., "if unclear, list possible interpretations")
- **Risk:** Agent proceeds with wrong assumptions, silent failures

**6. No memory/context awareness:**
- No instruction on using conversation history
- No guidance on maintaining consistency across turns
- No prompt to reference previous tool results
- **Risk:** Agent repeats work, ignores context, contradicts prior responses

### Duplicated & Conflicting Prompts

**Duplication:**
- Tool description duplication: stored in `Tool.description` + repeated in `to_llm_schema()` + rebuilt in LocalStub's `_build_system_prompt()`
- Error message generation duplicated: Orchestrator + Executor both construct failure messages
- Fallback logic duplication: LocalStubProvider's `_fallback_complete()` reimplements keyword heuristics separate from agent logic

**Conflicts:**
- **Iteration control conflict:** Orchestrator enforces `max_iterations` but no prompt tells LLM this exists
  - LLM may attempt to loop indefinitely; user sees abrupt cutoff message
  - Timeout message blames user: `"break down your request"` instead of explaining iteration limit
- **Tool availability conflict:** `tool_called_once` flag hides tools after first call [orchestrator.py](orchestrator.py#L100)
  - No prompt explains this to LLM → model confusion when tools disappear
  - Logic unclear: is this intentional throttling or bug?
- **Language conflict:** LocalStub instructs Russian, but tool schemas in English
  - Model receives: Russian system prompt → English tool names/descriptions → Russian/English messages
  - No instruction on which language to prefer

### Hallucination & Drift Risks

**High-risk areas:**

1. **Tool parameter hallucination:**
   - No few-shot examples in prompt showing correct parameter usage
   - JSON schema validation happens AFTER LLM call → wasted tokens, retry loops
   - No instruction: "parameters must match schema exactly"
   - **Current state:** Executor catches invalid parameters, adds error to memory, loop continues [orchestrator.py](orchestrator.py#L133-L163)
   - **Risk:** LLM invents parameters, ignores required fields, uses wrong types

2. **Capability hallucination:**
   - No explicit list of what agent CAN'T do
   - When tool fails → gap_detector suggests alternatives, but LLM may already have hallucinated solution
   - No prompt instruction: "only use provided tools, never simulate tool behavior"
   - **Risk:** LLM fabricates tool outputs, pretends to execute unavailable actions

3. **Prompt drift over conversation:**
   - Memory truncation at 90% capacity with no prompt update [conversation.py](conversation.py#L50-L51)
   - No system message refresh/re-injection after truncation
   - LocalStub's system prompt only sent at conversation start
   - **Risk:** Long conversations lose agent identity, tool format rules forgotten

4. **Context window blowup:**
   - Tool results added verbatim to memory [orchestrator.py](orchestrator.py#L169-L174)
   - No truncation, summarization, or token counting
   - Large file reads/command outputs pollute context
   - **Risk:** Context overflow, token limit exceeded, conversation aborted

5. **Error amplification:**
   - Failed tool results added to memory as raw error strings
   - LLM re-reads failures on each iteration → may fixate on errors
   - No instruction: "ignore previous errors if user clarifies intent"
   - **Risk:** Agent stuck in error loop, repeatedly retrying failed approach

### Agent Stability Risks

**Immediate risks for production:**

1. **No prompt governance:**
   - Any developer can modify prompts without review
   - No A/B testing, no rollback mechanism
   - No metrics on prompt effectiveness (success rate, token usage)

2. **Provider-specific behavior divergence:**
   - GroqProvider (no prompt) vs. LocalStubProvider (Russian prompt) produce different agent personas
   - No standardization test to ensure equivalent behavior
   - **Impact:** Agent behavior changes when switching providers

3. **Brittle tool format parsing:**
   - LocalStub expects regex extraction of `<function=...>` format [local.py](local.py#L243-L272)
   - GroqProvider expects native tool_calls objects
   - No validation that prompt instructions match parser expectations

4. **Uncontrolled iteration termination:**
   - No prompt guidance on when task is "complete"
   - LLM decides to stop by returning no tool_calls → implicit, unreliable
   - Agent may stop prematurely or loop unnecessarily

5. **No degradation handling:**
   - When Ollama unavailable → fallback to keyword heuristics with hardcoded Russian message [local.py](local.py#L203-L210)
   - No prompt adjustment for degraded mode
   - User experience breaks silently

### Summary

**Current state:** Prompts are **scattered, inconsistent, and implicit**. No system prompt for main provider (Groq), hardcoded Russian prompt for fallback provider (Local), and zero separation between code logic and agent instructions.

**Critical issues:**
- **No role definition** for GroqProvider (primary LLM)
- **Language mixing** (Russian/English) without explicit handling
- **No tool usage guidelines** beyond brief descriptions
- **No output format constraints** or safety instructions
- **High hallucination risk** due to missing constraints and examples

**Stability risks:**
- Prompts drift between providers and across conversation length
- No governance, versioning, or testing for prompt changes
- Agent behavior undefined under common failure modes (tool errors, truncation, degradation)

## 5. Codebase Health Assessment

### Overall Health Summary

**Grade: C+ (Acceptable but needs attention)**

The codebase demonstrates solid foundational structure with clear module separation and established patterns (dataclasses, abstract base classes, async/await). However, it exhibits moderate coupling, incomplete abstraction enforcement, and significant testing/observability gaps. Technical debt is accumulating in integration points and configuration handling.

**Strengths:**
- Well-organized module hierarchy (tools/, core/, llm/, memory/, safety/, gap_analyzer/)
- Consistent use of dataclasses for data structures (ToolResult, ToolParameter, LLMResponse, etc.)
- Abstract base classes enforce interface contracts (Tool, LLMProvider)
- Async/await consistently applied throughout
- Exception hierarchy is explicit and discriminates between retry/non-retry failures
- Tool registry provides clean registry pattern for plugin system

**Weaknesses:**
- Tight coupling in core orchestration (Orchestrator instantiates 5+ dependencies)
- Configuration validation incomplete; no consistency checks
- Memory persistence declared but not implemented (MemorySettings.persist_to_disk unconnected)
- Safety layer bypassed in execution flow (SafeExecutor not integrated)
- Import patterns create circular dependency risk
- No protocol interfaces for extensibility

---

### Critical Issues (Must Fix)

**1. Tangled Initialization & Dependency Coupling**

**Location:** [main.py](main.py#L31-L60), [orchestrator.py](core/orchestrator.py#L29-L54)

**Problem:**
- `_create_orchestrator()` in main.py directly instantiates 8+ objects: Orchestrator, Planner, Executor, GapDetector, GapResearcher, ToolProposer, ConversationMemory, ToolRegistry
- Orchestrator constructor chains more dependencies internally
- No dependency injection; hard-coded to specific implementations
- Tests must initialize full system to test single components
- Swapping implementations (e.g., different memory backend) requires modifying main.py

**Impact:**
- Cannot unit test components in isolation
- Changes to Orchestrator signature break all initialization code
- Fragile composition logic scattered between main.py and orchestrator.py

**Example:**
```python
# main.py line 58 - Orchestrator instantiation is tightly coupled
orchestrator = Orchestrator(
    llm_provider=llm,
    tool_registry=registry,
    memory=memory,
    max_iterations=config.agent.max_iterations
)
```

---

**2. Safety Layer Disconnected from Execution**

**Location:** [safety/executor.py](safety/executor.py), [core/executor.py](core/executor.py#L40-L68)

**Problem:**
- `SafeExecutor` exists but is NOT called during tool execution
- Actual tool execution happens in `Executor.execute_tool()` which has no safety checks
- `ConfirmationPrompt`, `AuditLogger`, `WhitelistManager` created but unused in flow
- Risk levels defined on tools (`Tool.risk_level`) but never checked at execution time
- Human approval logic never invoked
- Audit logging never triggered

**Impact:**
- HIGH risk tools execute without confirmation
- No executable safety policy (exists in code but not in behavior)
- Designed safety feature is completely bypassed

**Evidence:**
- SafeExecutor.py has `execute_safely()` method that validates and confirms
- Orchestrator never calls it; calls `executor.execute_tool()` directly
- Confirmation prompt never appears in practice

---

**3. Configuration Broken Contract**

**Location:** [config.py](config.py#L49-L52)

**Problem:**
- `MemorySettings.persist_to_disk=True` by default, but ConversationMemory has no persistence code
- In-memory deque only; no save/load methods exist
- Storage path configured (`storage_path = "./.jarvis/memory"`) but never used
- No validation that path is writable or that persistence will work
- Config promises persistence; code silently ignores it

**Impact:**
- User expects persistence; gets silent failure
- No error on startup; failure only apparent after restart
- Configuration creates false contract

---

**4. Responsibility Boundary Violations**

**Location:** [tools/discovery.py](tools/discovery.py#L73-L103), [tools/loader.py](tools/loader.py#L25-L70), [tools/registry.py](tools/registry.py#L1-L40)

**Problem:**
- **Discovery** discovers AND deduplicates
- **Loader** loads AND validates
- **Registry** manages AND serves as configuration store
- Responsibilities overlap: who is accountable for deduplication? validation? configuration?

**Example confusion:**
```python
# discovery.py does deduplication (_seen_names set)
# loader.py does validation (validate_tool_class)
# registry.py does registration (with duplicate check)
# Result: Responsibility is split; bugs can hide in the cracks
```

**Impact:**
- Unclear which component should catch duplicate tool registrations
- Bug in one component isn't isolated
- Hard to test each component independently
- Adding new discovery source requires understanding all three

---

**5. Missing Implementation: Persistence Layer**

**Location:** [memory/conversation.py](memory/conversation.py#L1-L80)

**Problem:**
- `persist_to_disk` configuration exists but no code implements it
- No `save()` or `load()` methods
- Conversation lost on shutdown
- DeserializationError or serialization format not defined
- Storage backend not connected

**Impact:**
- Configuration lie; users think conversations persist
- No way to implement features that depend on persistence
- Memory state is fragile

---

### Non-Critical But Concerning Issues

**1. Configuration Pattern Duplication**

**Location:** [main.py](main.py#L37-L44), [config.py](config.py#L1-L80)

**Problem:**
- `get_config()` used to read settings
- BUT also: `os.getenv("USE_LOCAL_LLM", ...)` in main.py
- Mixed patterns: Pydantic Settings + manual env vars
- No single source of truth for environment handling
- Difficult to test different configurations

**Recommendation:** Centralize all env var reading in config.py; main.py uses only `get_config()`

---

**2. Implicit Tool Availability Logic (Unclear Ownership)**

**Location:** [orchestrator.py](core/orchestrator.py#L96-L100)

**Problem:**
```python
tool_called_once = False
...
llm_tools = self.tool_registry.get_llm_schemas() if not tool_called_once else None
```

- Logic comment missing: why are tools hidden after first call?
- Implicit state machine; not a class property
- Unclear what this achieves: force summarization? prevent tool looping?
- No test validates this behavior is intentional

**Impact:**
- Developer reading code cannot understand intent
- Future changes may break this without noticing
- Difficult to reason about or maintain

---

**3. Error Handling Scattered & Inconsistent**

**Location:** [executor.py](core/executor.py#L40-L68), [orchestrator.py](core/orchestrator.py#L100-L150), [llm/groq.py](llm/groq.py)

**Problem:**
- Executor catches exceptions in try/catch, returns ToolResult with error
- Orchestrator catches LLM errors and adds to memory as text
- Different components have different error strategies
- Error context lost at layer boundaries
- No structured error logging (error object, not just string)

**Example:**
```python
# executor.py wraps errors in ToolResult
except Exception as e:
    return ToolResult(success=False, output=None, error=str(e))

# orchestrator.py catches and logs as text
except LLMError as e:
    logger.error(f"LLM error: {e}")
```

**Impact:**
- Hard to trace error origin
- Stack traces lost
- Cannot attach context (request ID, tool name, etc.)
- Difficult to debug failures

**Recommendation:** Use structured logging with context; pass exceptions through layers

---

**4. Memory Truncation Warning Insufficient**

**Location:** [memory/conversation.py](memory/conversation.py#L47-L50)

**Problem:**
```python
if len(self._messages) >= self.max_length * 0.9:
    logger.warning(f"Memory nearing limit: {len(self._messages)}/{self.max_length}")
```

- Only warns at 90%; does NOT prevent truncation
- Deque silently drops messages when full
- No event/callback when truncation occurs
- LLM may see incomplete context with no indication

**Impact:**
- Silent context loss
- Agent reasoning degrades without indication
- Difficult to diagnose conversation failures

---

**5. Testing Gaps**

**Current:** 15 unit test files covering tools, registry, discovery, safety, memory, logging, gap_analyzer, LLM providers

**Missing:**
- Integration tests for end-to-end ReAct loop
- Tests for configuration consistency validation
- Tests for persistence layer (no code to test)
- Tests for memory truncation behavior
- Tests for error recovery and retry logic
- No load/stress tests
- No prompt injection/safety tests

**Impact:**
- Cannot validate orchestration works correctly
- Regression risks when refactoring core flow
- Safety assumptions untested

---

**6. Inconsistent Logging Pattern**

**Location:** Throughout codebase (orchestrator.py, executor.py, registry.py, discovery.py)

**Problem:**
- Some modules use `logger = logging.getLogger(__name__)` (good)
- Some log with plain strings: `logger.info("message")`
- Some log with extra context: `logger.info("msg", extra={"request_id": ...})`
- Inconsistent use of debug vs. info levels
- No correlation ID propagated through layers

**Impact:**
- Cannot trace request through system
- Log aggregation difficult
- Debugging distributed issues impossible

---

**7. Tool Descriptions Serve Double Duty (Leaky Abstraction)**

**Location:** [tools/base.py](tools/base.py#L40-L60), [tools/registry.py](tools/registry.py#L100-L130)

**Problem:**
- `Tool.description` used for:
  1. LLM instruction (provided to LLM in tool schema)
  2. Tool metadata (displayed to users)
  3. Registry documentation
- Single field must serve 3 purposes
- Changing for one use case breaks others
- No way to provide LLM-specific vs. user-facing descriptions

**Impact:**
- Cannot optimize descriptions for LLM reasoning
- Cannot customize user-facing help text
- Tool descriptions are compromises

---

**8. Hardcoded Builtin Tools**

**Location:** [tools/discovery.py](tools/discovery.py#L76-L85)

**Problem:**
```python
from jarvis.tools.builtin import (
    EchoTool,
    FileReadTool,
    FileWriteTool,
    ListDirectoryTool,
    ShellExecuteTool,
    WebFetchTool,
    WebSearchTool,
)
```

- Tools hardcoded in import statement
- Not dynamic; adding tool requires code change + import
- Builtin tools not discoverable via file system
- Cannot enable/disable builtin tools via config

**Impact:**
- Plugin system incomplete; builtins are special case
- Cannot dynamically load/unload tools
- Configuration cannot control available tools

---

**9. No Protocol Interfaces for Extension**

**Problem:**
- Tool interface is abstract class (good)
- LLMProvider interface is abstract class (good)
- But no Protocols defined for optional capabilities
- Tools cannot declare optional features (e.g., streaming)
- LLMProviders cannot signal unsupported features (e.g., tool calling)

**Impact:**
- Cannot handle provider-specific capabilities cleanly
- Feature negotiation requires try/except
- Hard to support diverse providers (some support tools, some don't)

---

**10. Request ID Tracking Incomplete**

**Location:** [orchestrator.py](core/orchestrator.py#L71-L72), [observability/__init__.py](observability/__init__.py)

**Problem:**
- `set_request_id()` called in orchestrator
- But NOT propagated to: Executor, Registry, LLM calls, Tool executions
- Logging can reference request_id but most code doesn't
- No cleanup (`clear_request_id()`)

**Impact:**
- Request tracing only partially implemented
- Log correlation breaks in tool execution
- Difficult to diagnose request flow

---

### Code Readability & Structure Assessment

**Positive:**
- Clear module organization
- Consistent naming conventions
- Use of dataclasses prevents boilerplate
- Docstrings present on most classes/functions
- Type hints used consistently

**Concerns:**
- Long methods (Orchestrator.run is 260+ lines)
- Complex control flow in orchestrator (implicit state, multiple loop breaks)
- Comments missing on non-obvious logic (e.g., tool_called_once flag)
- Method names sometimes obscure intent (e.g., `_discover_builtin` returns list, not side effect)
- Nested try/catch blocks reduce readability

---

### Technical Debt Summary

| Category | Severity | Count | Notes |
|----------|----------|-------|-------|
| Tight coupling | High | 3 | main.py, orchestrator, initialization |
| Incomplete implementation | High | 2 | Persistence, Safety integration |
| Responsibility violations | Medium | 3 | Discovery/Loader/Registry overlap |
| Error handling inconsistency | Medium | 4 | Scattered try/catch patterns |
| Configuration duplication | Medium | 2 | env vars + Pydantic |
| Testing gaps | Medium | 5+ | Missing integration/safety/load tests |
| Observability gaps | Low | 3 | Request ID, logging, metrics |
| Code clarity | Low | 2 | Long methods, implicit logic |

**Estimated effort to address:**
- Critical issues: 3-5 days
- Non-critical issues: 2-3 days
- Testing coverage: 5-7 days

## 6. Existing Interfaces & Contracts

### Explicit Interfaces

**1. Tool Interface** ([tools/base.py](tools/base.py#L39-L113))

Contract:
```python
class Tool(ABC):
    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    capabilities: list[str] = field(default_factory=list)

    async def execute(**kwargs) -> ToolResult
    def get_parameters() -> list[ToolParameter]
    def to_llm_schema() -> dict  # OpenAI function calling format
    def to_manifest() -> dict     # Storage/discovery format
```

**Guarantees:**
- Tool.execute() returns ToolResult with success/output/error fields
- ToolResult.success is boolean; ToolResult.error is string or None
- get_parameters() returns list of ToolParameter with name/type/description/required
- to_llm_schema() produces OpenAI function calling format with properties/required fields

**Missing:**
- No lifecycle hooks (init/cleanup/validate/pre_execute/post_execute)
- No contract for execute() exceptions (when to throw vs. return error in ToolResult)
- No specification for output format (string? dict? Any?)
- No capability negotiation protocol (tools declare capabilities list but no consumer interface)
- No timeout contract (tools may block indefinitely)
- No streaming/chunked output support

---

**2. LLMProvider Interface** ([llm/base.py](llm/base.py#L26-L70))

Contract:
```python
class LLMProvider(ABC):
    async def complete(messages, tools, temperature, max_tokens) -> LLMResponse
    async def validate_connection() -> bool
    @property model_name -> str
    @property provider_name -> str
```

**Guarantees:**
- complete() accepts message list with role/content dicts
- Returns LLMResponse with content (str), tool_calls (list | None), stop_reason, tokens_used
- ToolCall has name/arguments/id fields

**Missing:**
- No specification for tool format (assumes OpenAI function calling; LocalStubProvider uses different format)
- No protocol for providers that don't support tools (graceful degradation undefined)
- No streaming interface
- No token counting/embeddings/batch processing support
- No retry/timeout handling specified at interface level
- No exception hierarchy (what errors should caller expect?)
- No system prompt contract (GroqProvider has none; LocalStubProvider has hardcoded Russian prompt)

---

**3. ToolRegistry Interface** ([tools/registry.py](tools/registry.py#L10-L148))

Contract:
```python
class ToolRegistry:
    def register(tool: Tool) -> None
    def unregister(name: str) -> bool
    def get(name: str) -> Tool | None
    def get_all() -> list[Tool]
    def find_by_capability(capability: str) -> list[Tool]
    def find_by_risk_level(risk_level: RiskLevel) -> list[Tool]
    def get_llm_schemas() -> list[dict]
    def validate_parameters(tool_name: str, **kwargs) -> tuple[bool, str]
```

**Guarantees:**
- register() raises ValueError if tool name already exists
- get() returns None for unknown tools
- validate_parameters() returns (is_valid: bool, error_msg: str)

**Missing:**
- No tool versioning (name collision = hard error)
- No lazy loading (all tools kept in memory)
- No tool dependency declaration/resolution
- No namespace collision handling (e.g., two tools named "search" from different sources)
- No registration callbacks or hooks
- No query interface for complex tool selection (e.g., "find tools that handle PDFs")

---

**4. ConversationMemory Interface** ([memory/conversation.py](memory/conversation.py#L11-L125))

Contract:
```python
class ConversationMemory:
    def add_message(role: str, content: str) -> None
    def get_messages() -> list[dict]
    def get_recent(count: int) -> list[dict]
    def clear() -> None
    def size() -> int
    def is_empty() -> bool
    def to_dict() -> dict
```

**Guarantees:**
- add_message() accepts roles: user/assistant/system/tool (warns and coerces on unknown)
- get_messages() returns chronological list of {role, content} dicts
- Automatic truncation via deque maxlen; warns at 90% capacity

**Missing:**
- No persistence interface (persist_to_disk config exists but no save()/load() methods)
- No serialization format defined
- No conversation ID or session management
- No message ID or versioning
- No search/filter interface
- No summarization hook for truncation
- No event notification when messages added/truncated

---

**5. Orchestrator Interface** ([core/orchestrator.py](core/orchestrator.py#L20-L261))

Contract:
```python
class Orchestrator:
    def __init__(llm_provider, tool_registry, memory, max_iterations)
    async def run(user_input: str) -> str
```

**Guarantees:**
- run() returns final response string
- ReAct loop: Think → Act → Observe, up to max_iterations
- Handles tool execution and error recovery
- Adds messages to memory during execution

**Missing:**
- No stop condition protocol (LLM decides by not returning tool_calls; unclear contract)
- No streaming response interface
- No cancellation support (cannot interrupt long-running loop)
- No checkpoint/resume capability
- No observability hooks (cannot inject monitoring between loop iterations)
- No multi-user context (assumes single-user conversation)

---

**6. Executor Interface** ([core/executor.py](core/executor.py#L11-L93))

Contract:
```python
class Executor:
    def __init__(tool_registry: ToolRegistry)
    async def execute_tool(tool_name: str, arguments: dict) -> ToolResult
    def get_stats() -> dict
```

**Guarantees:**
- execute_tool() returns ToolResult (never throws)
- Validates tool existence and parameters before execution
- Catches all tool exceptions and wraps in ToolResult.error

**Missing:**
- No pre-execution hooks (for safety checks, logging, metrics)
- No timeout enforcement (tools can block indefinitely)
- No parallel execution despite max_parallel_executions config existing
- No execution context (request ID not propagated to tools)
- No resource limits (memory, CPU, file handles)

---

**7. SafeExecutor Interface** ([safety/executor.py](safety/executor.py#L14-L153))

Contract:
```python
class SafeExecutor:
    def __init__(confirmation, whitelist, auditor, require_confirmation_for)
    async def execute(tool: Tool, **kwargs) -> ToolResult
```

**Guarantees:**
- Checks whitelist before execution (if configured)
- Requests user confirmation for risk levels in require_confirmation_for list
- Logs to audit logger (if configured)
- Returns ToolResult with denied status if user rejects

**Status:** **DISCONNECTED** - SafeExecutor exists but is not invoked by Orchestrator or Executor

---

**8. ConfirmationPrompt Interface** ([safety/confirmation.py](safety/confirmation.py#L9-L123))

Contract:
```python
class ConfirmationPrompt:
    async def request_confirmation(operation, tool_name, parameters, reason) -> bool
    async def request_confirmation_with_retry(operation, tool_name, parameters, reason, max_retries) -> bool
```

**Guarantees:**
- Returns True if user approves, False if denied
- Displays formatted prompt with tool/operation/parameters
- Retries on invalid input (with max_retries)

**Status:** Created in main.py but never used (SafeExecutor is disconnected)

---

**9. ToolDiscovery Interface** ([tools/discovery.py](tools/discovery.py#L20-L195))

Contract:
```python
class ToolDiscovery:
    def discover_all(include_builtin, config_file, custom_paths) -> list[Tool]
```

**Guarantees:**
- Returns validated Tool instances
- Deduplicates by name (first wins, logs warning for conflicts)
- Discovery order: builtin → config → directories

**Implicit contracts:**
- Builtin tools must be importable from jarvis.tools.builtin
- Config file must be YAML with tool specs
- Custom paths must contain Python modules with Tool subclasses

---

**10. Exception Hierarchy** ([core/exceptions.py](core/exceptions.py#L1-L65))

Explicit types:
```python
JarvisError(message, details)
├── ToolDiscoveryError
├── ToolLoadError
├── ToolExecutionError
├── RetryableError(message, attempt, max_attempts)
├── NonRetryableError
└── TimeoutError(message, timeout_seconds)
```

**Missing:**
- LLMError not defined in exceptions.py (imported from where?)
- No clear contract for which errors are retryable
- No error correlation (request ID not attached to exceptions)

---

### Implicit Contracts & Assumptions

**1. Message Format Assumption**

**Between:** Orchestrator ↔ LLMProvider ↔ Memory

**Assumption:** Messages are dicts with "role" and "content" keys
- Orchestrator: `messages = self.memory.get_messages()` passes directly to `llm.complete(messages=messages)`
- LLMProvider: Assumes messages list with role/content format
- Memory: Stores {role, content} dicts

**Risk:** No validation that memory format matches LLM expectations; format mismatches silent

---

**2. Tool Schema Format Leakage**

**Between:** Tool ↔ ToolRegistry ↔ LLMProvider

**Assumption:** to_llm_schema() produces OpenAI function calling format
- Tool.to_llm_schema() hardcoded to OpenAI format ([base.py#L77-L113](base.py#L77-L113))
- GroqProvider expects this format (Groq API is OpenAI-compatible)
- LocalStubProvider expects DIFFERENT format: `<function=name(params)></function>` ([local.py#L243-L272](local.py#L243-L272))

**Contract violation:** Tool schema format tied to specific LLM provider format; LocalStub workaround uses regex parsing

**Risk:** Cannot support providers with different tool calling conventions without modifying Tool base class

---

**3. Tool Availability Implicit Logic**

**Between:** Orchestrator ↔ ToolRegistry

**Assumption:** Tools hidden after first call ([orchestrator.py#L100](orchestrator.py#L100))
```python
llm_tools = self.tool_registry.get_llm_schemas() if not tool_called_once else None
```

**No contract on:**
- Why tools are hidden (force summarization? prevent looping?)
- How LLM should behave when tools disappear
- Whether this is intentional or bug

**Risk:** LLM confusion when tools vanish; no prompt explains this behavior

---

**4. Error Handling Strategy Divergence**

**Between:** Executor ↔ Orchestrator ↔ LLM

**Inconsistent contracts:**
- Executor catches all exceptions → returns ToolResult with error string
- Orchestrator catches LLM exceptions → adds error text to memory and continues
- Gap analyzer triggered on tool failure → constructs suggestions, breaks loop

**No agreement on:**
- When to retry (Executor doesn't retry; Orchestrator uses retry_async wrapper)
- How to propagate context (stack traces lost, error strings only)
- When to abort vs. continue loop

---

**5. Request ID Propagation Incomplete**

**Between:** Orchestrator → Executor → Tool

**Assumption:** Request ID set via ContextVar propagates automatically
- Orchestrator calls `set_request_id()` ([orchestrator.py#L71-L72](orchestrator.py#L71-L72))
- Logging configured to read from ContextVar ([observability/logging.py#L28-L31](observability/logging.py#L28-L31))

**Missing propagation:**
- Executor.execute_tool() does not access request_id
- Tool.execute() has no context parameter
- Retry logic in resilience.py doesn't preserve request_id across retries

**Risk:** Request correlation breaks during tool execution; logs incomplete

---

**6. Configuration Consistency Not Enforced**

**Between:** main.py ↔ Config ↔ Components

**Implicit assumptions:**
- If persist_to_disk=True, ConversationMemory will persist (NOT IMPLEMENTED)
- If groq_api_key empty, fallback to LocalStubProvider (manual check in main.py)
- max_parallel_executions exists but Executor never executes in parallel

**No validation:**
- Config inconsistencies not caught at startup
- Components may read config values that are ignored

---

**7. Memory Truncation Side Effects**

**Between:** Memory ↔ Orchestrator ↔ LLM

**Assumption:** Deque auto-truncation is transparent
- ConversationMemory uses `deque(maxlen=max_length)` ([conversation.py#L31](conversation.py#L31))
- Oldest messages silently dropped when full
- Orchestrator calls `memory.get_messages()` unaware of truncation

**No contract on:**
- Whether system messages are protected from truncation
- How to notify LLM that context is incomplete
- When to trigger summarization instead of dropping

**Risk:** LLM loses critical context; agent forgets early conversation

---

**8. Tool Parameter Validation Timing**

**Between:** Executor ↔ ToolRegistry ↔ Tool

**Validation happens AFTER LLM call:**
1. LLM generates tool_calls with arguments
2. Executor calls registry.validate_parameters()
3. If invalid: error added to memory, loop continues

**No contract on:**
- Schema sent to LLM matches validation schema used by registry
- LLM receives validation errors (currently added to memory as text)
- Whether validation failures should count toward max_iterations

**Inefficiency:** Wasted LLM tokens on parameter hallucination; no pre-flight validation

---

**9. Discovery Deduplication Strategy**

**Between:** ToolDiscovery ↔ ToolLoader ↔ ToolRegistry

**Implicit behavior:** First tool wins on name collision ([discovery.py#L34](discovery.py#L34))
- Discovery maintains _seen_names set
- Logs warning for duplicates but doesn't fail
- Registry.register() throws ValueError on duplicate

**Inconsistency:**
- Discovery allows duplicates (with warning)
- Registry forbids duplicates (with exception)
- No configuration to choose strategy (fail vs. override vs. namespace)

---

**10. SafeExecutor Bypassed**

**Between:** Orchestrator ↔ Executor ↔ SafeExecutor

**Assumption (VIOLATED):** High-risk tools require confirmation
- Tool.risk_level defines LOW/MEDIUM/HIGH
- Tool.requires_confirmation flag exists
- SafeExecutor implements confirmation logic

**Reality:**
- Orchestrator calls Executor.execute_tool() directly
- SafeExecutor never invoked
- Confirmation/whitelist/audit never triggered

**Contract broken:** Safety layer exists in code but not in execution path

---

### Data Flow Analysis

**1. User Input → Response Flow**

```
User input (string)
  → main.py: creates Orchestrator
  → Orchestrator.run(user_input)
      → memory.add_message("user", user_input)
      → memory.get_messages() → messages list
      → llm.complete(messages, tools) → LLMResponse
      → if tool_calls:
          → executor.execute_tool(name, args) → ToolResult
          → memory.add_message("tool", result)
          → LOOP
      → else:
          → memory.add_message("assistant", response.content)
          → RETURN response.content
```

**Coupling points:**
- Memory format must match LLM message format (implicit)
- Tool schema format tied to LLM provider (implicit)
- ToolResult.output converted to string for memory (data loss if structured)

---

**2. Tool Discovery → Registration Flow**

```
main.py: _create_orchestrator()
  → ToolDiscovery.discover_all()
      → _discover_builtin() → imports from jarvis.tools.builtin
      → _discover_from_config() → ToolLoader.load_from_spec()
      → _discover_from_directory() → ToolLoader.load_from_path()
      ↓
  list[Tool] (validated instances)
      ↓
  → for tool in discovered_tools:
      → registry.register(tool)
```

**Coupling:**
- Discovery hardcodes builtin imports ([discovery.py#L76-L85](discovery.py#L76-L85))
- Loader introspects classes for Tool subclass (reflection-based)
- Registry has no visibility into discovery sources (cannot report provenance)

---

**3. Configuration → Component Initialization**

```
get_config() (Pydantic Settings)
  → reads .env + environment variables
  → returns Config object
      ↓
main.py:
  ├→ LLMProvider(api_key=config.llm.groq_api_key, model=config.llm.model)
  ├→ ConversationMemory(max_length=config.memory.max_conversation_length)
  └→ Orchestrator(max_iterations=config.agent.max_iterations)
```

**Shared state:**
- get_config() called multiple times (cached by Pydantic Settings)
- Manual env var checks in main.py bypass config system (USE_LOCAL_LLM, LOCAL_LLM_MODEL)

**Inconsistency:**
- Some config via Pydantic Settings
- Some config via os.getenv() in main.py
- No single initialization boundary

---

**4. Logging & Observability Flow**

```
Orchestrator.run()
  → set_request_id() → ContextVar[request_id]
      ↓
  logger.info(..., extra={"request_id": request_id, ...})
      ↓
  StructuredFormatter reads ContextVar
      ↓
  Log output with request_id field
```

**Broken propagation:**
- request_id set in Orchestrator
- NOT propagated to: Executor, Tool.execute(), LLM calls
- ContextVar should propagate through async calls but logs don't show it

---

**5. Gap Analysis Trigger Flow**

```
Orchestrator.run()
  → executor.execute_tool() → ToolResult(success=False)
      → if not result.success:
          → gap_detector.detect_from_error()
          → gap_researcher.research_solution()
          → tool_proposer.propose_tool()
          → construct response with suggestions
          → BREAK loop
```

**Tight coupling:**
- Gap analysis triggered inline in Orchestrator ReAct loop
- No separation of concerns (orchestrator knows about gap_detector internals)
- Gap analysis results added directly to memory as text

---

### Missing Contracts

**1. Tool Lifecycle Protocol**

**Need:**
- Tool.initialize() - setup resources (DB connections, file handles)
- Tool.cleanup() - release resources
- Tool.validate_environment() - check prerequisites
- Tool.health_check() - verify tool is functional

**Currently:** Tools instantiated once at startup; no lifecycle management

---

**2. LLM Capability Negotiation**

**Need:**
- LLMProvider.supports_tools() -> bool
- LLMProvider.supports_streaming() -> bool
- LLMProvider.max_context_length() -> int

**Currently:** Assumes all providers support tools; LocalStub uses workaround

---

**3. Memory Persistence Protocol**

**Need:**
- Memory.save(path: str) -> None
- Memory.load(path: str) -> None
- Memory.serialize() -> bytes
- Memory.deserialize(bytes) -> None

**Currently:** persist_to_disk config exists but no implementation

---

**4. Safety Check Protocol**

**Need:**
- Tool.assess_risk(**kwargs) -> RiskAssessment
- Executor.pre_execute_hook(tool, args) -> bool (proceed/abort)
- AuditLogger.log_execution(tool, args, result)

**Currently:** SafeExecutor exists but disconnected; no enforcement

---

**5. Streaming Response Protocol**

**Need:**
- LLMProvider.stream(messages, tools) -> AsyncIterator[LLMChunk]
- Orchestrator.run_streaming(user_input) -> AsyncIterator[str]

**Currently:** All responses buffered; no streaming support

---

**6. Tool Dependency Declaration**

**Need:**
- Tool.requires: list[str] - names of tools this tool depends on
- ToolRegistry.resolve_dependencies(tool_name) -> list[Tool]

**Currently:** No dependency management; tools assumed independent

---

**7. Error Recovery Protocol**

**Need:**
- RetryPolicy interface with strategy selection
- Clear designation: which exceptions are retryable
- Backoff/timeout configuration per operation

**Currently:** retry_async exists but not consistently applied; no protocol

---

**8. Multi-User/Session Protocol**

**Need:**
- ConversationMemory(session_id: str)
- Orchestrator.run(user_input, session_id: str)
- Request context with user_id, session_id

**Currently:** Single-user assumption; no session management

---

### Areas Requiring Formalization

**Critical:**

1. **Tool-LLM schema contract** - Tool.to_llm_schema() format varies by provider; needs provider-specific transformation layer
2. **Safety execution enforcement** - SafeExecutor must be wired into execution path; contract for when confirmations required
3. **Memory persistence contract** - Define save/load interface or remove persist_to_disk config
4. **Error propagation strategy** - Standardize: throw exceptions vs. return error objects; define retryable exceptions

**High Priority:**

5. **Request ID propagation** - Formalize how context flows through async calls; attach to Tool.execute() signature
6. **Tool lifecycle management** - Define init/cleanup hooks; resource management protocol
7. **Message format validation** - Explicit schema for memory ↔ LLM communication; catch format mismatches early
8. **LLM provider capabilities** - Negotiation protocol for tool support, context length, streaming

**Medium Priority:**

9. **Tool dependency resolution** - Declare and enforce dependencies between tools
10. **Configuration consistency validation** - Check config at startup; fail fast on invalid combinations
11. **Memory truncation policy** - Contract for what happens when memory full; notification mechanism
12. **Tool deduplication strategy** - Choose: fail, override, or namespace on collision; enforce consistently

**Lower Priority:**

13. **Streaming interface** - AsyncIterator protocol for LLM and Orchestrator
14. **Parallel tool execution** - Batch execution interface; resource limits
15. **Session management** - Multi-user context; conversation ID handling

---

### Summary

**Explicit Interfaces:** 10 well-defined (Tool, LLMProvider, ToolRegistry, Memory, Orchestrator, Executor, SafeExecutor, ConfirmationPrompt, ToolDiscovery, Exceptions)

**Critical Gaps:**
- Tool ↔ LLM schema format leakage (OpenAI format hardcoded)
- SafeExecutor disconnected from execution path (safety contract broken)
- Memory persistence declared but not implemented
- Request ID propagation incomplete

**Implicit/Problematic Contracts:**
- Message format assumptions (Memory → LLM) not validated
- Tool availability logic (tool_called_once) undocumented
- Error handling strategy inconsistent across components
- Configuration checked manually instead of validated at boundaries

**Data Flow Tight Coupling:**
- Orchestrator knows gap_detector/gap_researcher/tool_proposer internals
- Tool schema format tied to LLM provider implementation
- Memory stores strings; structured data lost during serialization

**Missing Formalization:**
- Tool lifecycle (init/cleanup)
- LLM capability negotiation
- Error recovery policy
- Multi-user/session context

## 7. Open Questions / TODO
