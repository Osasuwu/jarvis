# Jarvis Architecture

Version: 1.0
Date: 2026-03-20
Status: Active

## 1. System Overview

Jarvis is a management-oriented AI agent for software delivery operations.

Primary responsibilities:
- planning and decomposition,
- process supervision,
- issue/PR/project state coherence,
- controlled execution support.

## 2. Architectural Style

The system uses a centralized orchestration model with strict human oversight.

Why this model now:
- lowest coordination complexity,
- clear accountability point,
- strong fit for single-supervisor workflow.

## 3. High-Level Components

### Runtime Layer

- `core/orchestrator.py`: task loop and decision flow.
- `core/executor.py`: tool execution with safety integration.
- `core/factory.py`: dependency composition and bootstrap.

### Capability Layer

- `tools/`: registry, discovery, loading, builtin tools.
- `safety/`: confirmation, whitelist, audit.
- `memory/`: conversation state and persistence.

### Governance Layer

- `.github/`: process templates, checks, and automation.
- `docs/PROJECT_PLAN.md`: strategic source of truth.
- GitHub Project fields: Status, Priority, Phase, Area.

## 4. Delivery Control Flow

1. Human defines objective through issue hierarchy.
2. Agent executes one task through one PR.
3. Workflow checks enforce process quality.
4. Merge updates issue and parent progress.
5. Daily triage and weekly report drive next steps.

## 5. Safety and Guardrails

- Risky operations require explicit confirmation.
- Whitelist constrains sensitive execution paths.
- Audit trail records actions for review.
- CI and schema checks prevent process drift.

## 6. Current Constraints

Deferred capabilities are intentionally excluded from runtime decisions:
- self_improvement,
- multi-agent/debate,
- vector memory,
- marketplace,
- cloud sync.

## 7. Evolution Direction

The architecture evolves in this order:
1. Process reliability first.
2. Management capability expansion second.
3. Advanced autonomy only after governance stability is proven.
- Tool Registry: JSON files
- Conversation History: In-memory
- User Config: YAML

**Future:**
- Vector DB для семантического поиска инструментов
- SQLite для истории и состояния

### Безопасность

1. **Sandboxing:** изоляция выполнения опасных команд
2. **Whitelist:** разрешенные команды и пути
3. **Approval Chain:** обязательное подтверждение для HIGH risk
4. **Audit Log:** полная история действий

---

## Следующие шаги

1. ✅ **Phase 0:** Подготовка репозитория
2. 🚧 **Phase 1:** Реализация LLM Adapter и Tool Registry
3. ⏳ **Phase 2:** Orchestrator MVP
4. ⏳ **Phase 3:** Базовые инструменты
5. ⏳ **Phase 4:** Human-in-the-Loop
6. ⏳ **Phase 5:** Capability Gap Analyzer

---

**Статус документа:** Living Document — будет обновляться по мере развития проекта
