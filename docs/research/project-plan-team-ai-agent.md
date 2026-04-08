# Project Plan: Team AI Agent Infrastructure

> Version: 2.0
> Date: 2026-04-08
> Author: Petr
> Status: DRAFT — architecture redesigned around "complement, not restrict" principle

---

## 0. Core Principle: Complement, Not Restrict

У каждого в команде будет свой личный агент — настроенный под себя, со своим стилем работы. Общая система **не делает всех агентов одинаковыми**, а даёт доступ к общей информации, материалам и автоматизации.

**Что это значит:**
- Нет "единого агента для команды" — у каждого свой
- Shared layer предоставляет **контекст**, не навязывает **поведение**
- Каждый выбирает что брать из общих ресурсов
- Разные агенты, разные инструменты, разные workflow — это нормально

**Аналогия:** библиотека, не школа. Приходи, бери что нужно, работай как хочешь.

---

## 1. Executive Summary

### Problem
Команда (3 разработчика + техническая команда: 3D, инструменты, презентации) активно использует AI индивидуально. Каждый тратит время на объяснение контекста, повторяющуюся рутину, потерю решений между сессиями. Находки не переиспользуются. Все — early adopters, каждый настроил AI под себя.

### Solution
Построить **shared context layer** — общий слой знаний и автоматизации, к которому подключаются личные агенты:
1. **Shared Context** — качественные docs в проектах + общая база знаний команды
2. **Shared Automation** — GitHub Actions (auto-review, triage, CI-мониторинг) работает для всех
3. **Team Memory** — Supabase с общим и личным пространством, доступ через MCP / API / UI
4. **Agent Templates** — опциональные стартовые наборы для тех, кто хочет быстро начать

### Expected Outcome
- Снижение time-to-context на 80% (15 мин → 3 мин) — через качественные docs и shared memory
- Автоматизация PM-рутины на уровне репозиториев — auto-review, triage, CI-alerts
- Переиспользование находок — инструменты, решения, паттерны доступны всем
- Свобода выбора — каждый работает своим агентом/инструментом
- Масштабируемость — новый проект/человек подключается к shared layer

---

## 2. Team & Stakeholders

| Кто | Роль | AI usage | Что получает от проекта |
|-----|------|----------|------------------------|
| Пётр | Разработчик, архитектор AI-инфраструктуры | Claude Code (продвинутая настройка) | Масштабирует опыт на команду |
| Разработчики | Код, архитектура, review | Claude (уровень уточнить) | Shared context, автоматизация рутины |
| Техническая команда | Инструменты, презентации, AI adoption | claude.ai + AI tools | Единый контекст, structured research |

**Все early adopters.** Деления на пилот/основную группу нет — команда маленькая, внедряем всем сразу.

---

## 3. Competitive Landscape & Prior Art

### 3.1 Multi-Agent Frameworks (general-purpose)

| Framework | Подход | Stars | Для нас? |
|-----------|--------|-------|----------|
| **LangGraph** | Graph-based workflows, stateful | 27K searches/mo | Overkill — Python framework, мы на Claude Code native |
| **CrewAI** | Role-based agents, low boilerplate | 14.8K searches/mo | Интересная модель ролей, но опять Python-wrapper |
| **AutoGen** (Microsoft) | Conversational multi-agent | ~12K | Для research/brainstorming, не для dev pipeline |
| **MetaGPT** | Simulated dev team (CEO→PM→Dev) | ~45K stars | Closest to our vision, but Python-only |

**Вывод:** Все фреймворки — Python wrappers над LLM API. Мы на Claude Code native, и наш стек покрывает 80% без них. Брать идеи (role patterns, orchestration models), не брать код.

### 3.2 Shared Knowledge / Memory для команд

| Project | Подход | Релевантность |
|---------|--------|--------------|
| **[Knowledge Plane](https://github.com/camplight/knowledgeplane)** | MCP server + knowledge graph (ArangoDB) + vector embeddings. Multi-workspace, multi-agent, multi-tool. Background workers auto-consolidate facts into "knowledge cards". REST API + Next.js dashboard. Apache-2.0. | **HIGH** — наиболее полная реализация shared knowledge через MCP. Архитектура близка к нашему target state (Level 2-3) |
| **[Shared Memory MCP](https://github.com/haasonsaas/shared-memory-mcp)** | Context deduplication (10:1), incremental delta updates, work unit coordination. Снижает token usage с 48K до 8K per session. | MEDIUM — полезен для multi-agent coordination, менее для team sharing |
| **Memory Bank pattern** (Cline-originated) | Structured markdown: `projectbrief.md`, `activeContext.md`, `systemPatterns.md`, `progress.md`. Agent reads all at session start. Tool-agnostic. | **HIGH** — простой, работает с любым инструментом. Хорошая модель для Level 0-1 |

### 3.3 Claude Code-Specific Projects

| Project | Что делает | Релевантность |
|---------|-----------|--------------|
| **[wshobson/agents](https://github.com/wshobson/agents)** | Крупнейшая коллекция Claude Code агентов/skills. Community: forks (amurata/cc-tools), skills-manager (browse/install skills), bdarbaz/claude-code-stack (73+ agents, 100+ skills in presets). | **HIGH** — модель skill library. Можно взять за основу для Phase 4 agent templates |
| **[claude-code-best-practice](https://github.com/shanraisshan/claude-code-best-practice)** | Шаблон CLAUDE.md с best practices | MEDIUM — полезен для team onboarding |
| ~~claude-mpm~~ | Не найден на GitHub — возможно не опубликован | N/A |

### 3.3 Open-Source AI Coding Agents

| Agent | Подход | Для нас? |
|-------|--------|----------|
| **OpenHands** (ex-OpenDevin) | Open platform, sandboxed, multi-agent delegation, 77.6% SWE-bench | Может быть backend для тяжёлых задач (self-hosted) |
| **Cline** | IDE-embedded, review-first workflow | Альтернативный UX, но мы в Claude Code |
| **SWE-agent** (Princeton) | Research benchmark, не production | Нет |

### 3.4 Claude Agent SDK

- **Python + TypeScript**, `pip install claude-agent-sdk`
- **Headless mode** — `query()` без GUI, для CI/CD и серверных задач
- **Shared task lists** с dependency tracking между sub-agents
- **Custom tools** как in-process MCP servers
- **Skills support** — загружает `.claude/skills/` из filesystem

### 3.5 Индустриальные паттерны (из ресёрча)

Три подхода к sharing context между агентами в команде:

| Pattern | Как | Плюсы | Минусы |
|---------|-----|-------|--------|
| **A: Git-committed context** | CLAUDE.md, .cursorrules, memory-bank/ в repo | Работает с любым инструментом, version-controlled | Статичный per commit, нет real-time |
| **B: Shared MCP server** | Общая БД (Supabase/Qdrant/ArangoDB) через MCP | Real-time, cross-session, cross-tool | Только для MCP-совместимых инструментов |
| **C: Hybrid (рекомендуемый)** | Git docs (static) + MCP memory (dynamic) + REST API (universal) | Все инструменты получают доступ | Больше компонентов |

**Наш выбор: Pattern C (Hybrid)** — уже частично реализован:
- Git docs → CLAUDE.md per project (Level 0)
- MCP memory → mcp-memory/server.py + Supabase (Level 2, нужен team namespace)
- REST API → нужен для не-MCP агентов (Level 2)

**Ключевой вывод ресёрча:** никто в индустрии успешно не навязывает единообразие инструментов в командах. Ценность — в shared CONTEXT, не shared TOOLS. Подтверждает наш подход "complement, not restrict".

---

## 4. Requirements

### 4.1 Functional Requirements

#### Shared Context (Must Have)
- FR-1.1: Качественный CLAUDE.md в каждом активном проекте
- FR-1.2: Team knowledge repo с конвенциями, находками, шаблонами
- FR-1.3: Docs доступны через git — работают с любым инструментом
- FR-1.4: README: как получить контекст проекта за <3 мин

#### Shared Automation (Should Have)
- FR-2.1: GitHub Actions: auto-review на PR (claude-code-action)
- FR-2.2: Issue auto-triage (labels, priority)
- FR-2.3: CI monitoring с алертами
- FR-2.4: PR templates с контекстным body

#### Team Memory (Could Have)
- FR-3.1: Team namespace в Supabase (отделён от personal)
- FR-3.2: MCP endpoint для team memory
- FR-3.3: REST API для агентов без MCP
- FR-3.4: Read-only UI для людей
- FR-3.5: Протокол: что/как сохранять в team memory

#### Agent Templates (Want to Have)
- FR-4.1: Starter kit: CLAUDE.md + skills + .mcp.json template
- FR-4.2: Optional skill library (не обязательный — pick what you want)
- FR-4.3: AI delegation: issue → PR
- FR-4.4: Multi-agent PM (если команда растёт)

### 4.2 Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Time-to-context | <3 min с нуля для любого инструмента |
| Tool-agnosticism | Работает с Claude Code, Cursor, ChatGPT, без AI |
| No vendor lock-in | Docs = markdown in git. Memory = Supabase (portable) |
| Cost per developer | $0 для Level 0-1. <$20/month для Level 2+ |
| Security | No secrets in configs, SOC 2 compliance |
| Maintenance burden | <1h/week для team knowledge |
| Progressive adoption | Каждый уровень ценен без предыдущих |

---

## 5. Architecture

### 5.1 Core Concept: Shared Context Layer

Вместо "единой AI-системы для команды" строим **слой общего контекста**, к которому подключаются разные агенты. Слой состоит из 4 уровней, каждый опционален и добавляет ценность независимо:

```
┌─────────────────────────────────────────────────────────────┐
│                    SHARED CONTEXT LAYER                      │
│                                                             │
│  Level 0: Project Docs          Level 1: Team Knowledge     │
│  ┌────────────────────┐         ┌───────────────────────┐   │
│  │ Per-repo CLAUDE.md  │         │ team-knowledge repo   │   │
│  │ README, docs/       │         │ conventions/          │   │
│  │ ARCHITECTURE.md     │         │ findings/             │   │
│  │ .claude/skills/     │         │ templates/            │   │
│  └────────────────────┘         └───────────────────────┘   │
│                                                             │
│  Level 2: Team Memory           Level 3: Shared Automation  │
│  ┌────────────────────┐         ┌───────────────────────┐   │
│  │ Supabase (team ns)  │         │ GitHub Actions        │   │
│  │ decisions, findings │         │ auto-review on PRs    │   │
│  │ sprint context      │         │ CI monitoring         │   │
│  │ Access: MCP/API/UI  │         │ issue auto-triage     │   │
│  └────────────────────┘         └───────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
              ↑               ↑               ↑
       reads/writes     reads/writes     reads/writes
              │               │               │
       ┌──────┴───┐    ┌──────┴───┐    ┌──────┴───┐
       │  Petr's  │    │  Dev 2's │    │  Dev 3's │
       │  AI      │    │  AI      │    │  AI      │
       │ (Claude  │    │ (any     │    │ (any     │
       │  Code +  │    │  tool)   │    │  tool)   │
       │  MCP +   │    │          │    │          │
       │  memory) │    │  own     │    │  own     │
       │          │    │  config  │    │  config  │
       └──────────┘    └──────────┘    └──────────┘
```

### 5.2 Уровни (progressive adoption)

| Уровень | Что | Кому помогает | Инфраструктура | Стоимость |
|---------|-----|---------------|----------------|-----------|
| **0: Project Docs** | Качественные CLAUDE.md, README, docs/ в каждом репо | Всем — любой агент читает при открытии репо | Ноль — только дисциплина | Время на написание |
| **1: Team Knowledge Repo** | Git-repo с конвенциями, находками, шаблонами | Всем — markdown читается кем угодно | Один repo | Минимальная |
| **2: Team Memory** | Supabase с team namespace, доступ через MCP / API / UI | Агентам с MCP + всем через API/UI | Supabase (уже есть) + расширение MCP | Низкая |
| **3: Shared Automation** | GitHub Actions: auto-review, triage, CI-alerts | Проектам целиком, независимо от агентов | GitHub Actions per repo | Конфиг |

**Ключевое свойство:** каждый уровень работает без предыдущих. Level 3 (автоматизация) полезен даже без Level 2 (memory). Level 0 (docs) полезен без всего остального.

### 5.3 Team Memory: личное vs общее

```
Supabase Memory
├── personal (project=<user-slug>)     ← видит только owner
│   ├── Petr's agent memories
│   ├── Dev2's agent memories
│   └── Dev3's agent memories
│
├── team (project="team")              ← видят все
│   ├── decisions (architectural, process)
│   ├── findings (tools, patterns, bugs)
│   ├── sprint context (what's current focus)
│   └── conventions (agreed standards)
│
└── project-scoped (project="redrobot") ← видят все в проекте
    ├── architecture decisions
    ├── known issues / gotchas
    └── environment setup notes
```

Доступ:
- **Claude Code (MCP)** — `memory_recall(project="team")` / `memory_store(project="team")`
- **API** — REST endpoint для других агентов
- **UI** — Supabase dashboard / простая read-only страница
- **Export** — markdown dump для статического потребления

### 5.4 Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Knowledge base | Git repos (markdown) | Tool-agnostic, versioned, PRs for changes |
| Dynamic memory | Supabase (pgvector + RRF) | Already exists, cross-device, vector search |
| Memory access | MCP server (Claude Code) + REST API (other agents) | Multiple access paths |
| Automation | GitHub Actions + claude-code-action | Runs on repo, no per-agent setup needed |
| Agent runtime | Individual choice | Claude Code, Cursor, ChatGPT, none — all work |
| Configuration | CLAUDE.md per project (not per company) | Each project is self-contained |

---

## 6. Implementation Roadmap

> Принцип: каждая фаза приносит ценность сама по себе. Если остановимся на Phase 1 — уже лучше чем было. Нет зависимости "нужно всё или ничего".

### Phase 1: Shared Context (Неделя 1-2)
**Goal:** Общая информация доступна всем агентам/людям. Никто не объясняет контекст заново.

| Task | Owner | Effort | Deliverable |
|------|-------|--------|-------------|
| Собрание + обсуждение подхода | Пётр | 1h | Обратная связь, уточнения |
| Обработка результатов обсуждения | AI | 2h | Скорректированные приоритеты |
| Качественный CLAUDE.md в каждом активном проекте | Пётр + AI | 3h | Контекст проекта для любого агента |
| Team knowledge repo (conventions, findings, templates) | AI | 3h | Git repo с общей базой знаний |
| README: "как подключиться к shared context" | AI | 1h | Инструкция для разных инструментов |
| claude.ai Projects для не-кодеров | Пётр | 30min | CLAUDE.md как Project Knowledge |

**Что каждый получает:**
- Открыл проект → агент знает контекст (через CLAUDE.md)
- Нужна конвенция → team-knowledge repo
- Не-кодер → claude.ai с тем же контекстом

**Success criteria:**
- [ ] CLAUDE.md есть в каждом активном проекте
- [ ] Team knowledge repo создан и содержит первые 5+ документов
- [ ] Каждый член команды может получить проектный контекст за <3 мин

### Phase 2: Shared Automation (Недели 2-4)
**Goal:** Автоматизация работает на уровне репо — помогает всем, настраивается один раз.

| Task | Owner | Effort | Deliverable |
|------|-------|--------|-------------|
| GitHub Actions: auto-review на PR | AI | 3h | AI pre-review каждого PR |
| PR template с rich body | AI | 1h | Контекстные описания PR |
| Issue auto-triage workflow | AI | 4h | Новые issues → labels, priority |
| CI monitoring + alerts | AI | 2h | Алерт если CI сломан |
| Shared findings: "AI Guild" в team knowledge | Все | ongoing | Находки, паттерны, промпты |
| Baseline метрики | Пётр | 1h | Cycle time, review time — до/после |

**Что каждый получает:**
- PR автоматически получает AI pre-review (независимо от агента автора)
- Issues автоматически получают labels и priority
- CI-проблемы видны сразу

**Success criteria:**
- [ ] Каждый PR проходит AI pre-review
- [ ] 80% новых issues получают labels автоматически
- [ ] Baseline метрики зафиксированы

### Phase 3: Team Memory (Недели 4-8)
**Goal:** Динамическое общее знание — решения, находки, контекст спринта — доступно агентам.

| Task | Owner | Effort | Deliverable |
|------|-------|--------|-------------|
| Team namespace в Supabase | AI | 2h | Разделение personal/team/project |
| MCP endpoint для team memory | AI | 4h | memory_recall(project="team") |
| REST API для не-MCP агентов | AI | 4h | /api/team-memory для Cursor/ChatGPT |
| Простой read-only UI | AI | 3h | Веб-страница с team knowledge |
| Протокол: что сохраняется в team memory | Пётр + команда | 1h | Конвенция записи |
| Опрос #2: что помогает, что нет | Пётр | 30min | Feedback для корректировки |

**Что каждый получает:**
- Агент с MCP: `memory_recall(project="team")` → все решения команды
- Агент без MCP: REST API или UI
- Человек: UI или Supabase dashboard

**Success criteria:**
- [ ] 3+ решения/неделю сохраняются в team memory
- [ ] Каждый может прочитать team context через свой инструмент
- [ ] Метрики показывают улучшение (или объясняют почему нет)

### Phase 4: Agent Templates & Advanced (Недели 8+)
**Goal:** Опциональные стартовые наборы для тех, кто хочет глубже. Продвинутая автоматизация.

| Task | Owner | Effort | Deliverable |
|------|-------|--------|-------------|
| Starter kit: "Claude Code за 15 мин" | AI | 3h | CLAUDE.md + skills + .mcp.json template |
| Skill library (optional, pick what you want) | AI | 6h | /review-pr, /investigate, /write-test, ... |
| AI delegation: issue → PR | AI | 6h | Автоматическая реализация issues |
| Morning brief (team-wide) | AI | 3h | Утренний статус по проектам |
| Multi-agent: per-project PM (если нужно) | AI | 12h | PM agent prototype |

**Success criteria:**
- [ ] 1+ человек использует starter kit
- [ ] 3+ issues/неделю реализуются AI
- [ ] Команда считает AI частью процесса (survey)

---

## 7. Risk Register

| # | Risk | Probability | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | Shared context не читается — каждый продолжает объяснять контекст заново | MEDIUM | HIGH | Показать ценность на первом собрании. Если не работает — упростить формат, спросить что нужно |
| R2 | CLAUDE.md / docs устаревают | HIGH | MEDIUM | Обновление как часть PR (изменил код → обнови docs). Один ответственный per repo |
| R3 | AI code quality drops | MEDIUM | HIGH | Auto-review = pre-screening, не approval. Human review обязателен. Метрика: escaped defects |
| R4 | Team memory не наполняется | MEDIUM | MEDIUM | Начать с малого — Petr наполняет first, показывает value. Протокол: что сохраняем |
| R5 | Anthropic breaks/changes something | LOW | HIGH | Docs = markdown (portable). Memory = Supabase (portable). Low lock-in |
| R6 | Overengineering Phase 3-4 | MEDIUM | MEDIUM | Каждая фаза доказывает ценность до старта следующей. Kill criteria |
| R7 | One person dependency (Пётр) | HIGH | HIGH | Документировать всё. Team knowledge repo как bus factor mitigation |
| R8 | Scope creep: смешивание личного и командного | MEDIUM | MEDIUM | Личный AI = личный. Team system = shared context. Чёткая граница |
| R9 | Разные агенты = несовместимые форматы | LOW | MEDIUM | Shared layer = markdown (universal). Memory = REST API (universal) |

---

## 8. Success Metrics

### Quantitative (measure monthly)

| Metric | Baseline | Phase 1-2 Target | Phase 3-4 Target |
|--------|----------|------------------|------------------|
| Time-to-context (новый на проекте) | ~15 min | <3 min | <1 min |
| PR cycle time (commit → merge) | TBD | -20% | -40% |
| PR review turnaround | TBD | -30% (auto-review) | -50% |
| Escaped defects | TBD | Same or lower | -20% |
| Team findings documented/month | 0 | 5+ | 10+ |
| Team memory entries | 0 | 0 | 20+ |

### Qualitative (survey per phase)

- "Я не объясняю контекст заново" (agree/disagree)
- "Находки коллег мне доступны" (agree/disagree)
- "AI помогает мне работать лучше" (1-10)
- "Система не мешает мне работать по-своему" (agree/disagree)
- Top 3 полезных момента за период

---

## 9. Decision Log

| # | Decision | Date | Rationale | Alternatives Considered |
|---|----------|------|-----------|------------------------|
| D1 | Claude Code native, not custom Python framework | 2026-03-28 | 80% covered, Anthropic iterates fast | LangGraph, CrewAI, custom FastAPI |
| D2 | Supabase for shared memory | 2026-03-29 | Cross-device, existing, cheap | File-based, Redis, custom DB |
| D3 | GitHub Actions as event bus | 2026-04-05 | Already works, free, no new infra | Webhooks, polling, custom daemon |
| D4 | Phase-based rollout, not big bang | 2026-04-07 | Reduce risk, get feedback early | All at once, per-person rollout |
| D5 | Mandatory human review on all AI PRs | 2026-04-07 | Trust but verify, team confidence | Auto-merge for low-risk |
| D6 | **"Complement, not restrict"** | **2026-04-08** | **Каждый в команде имеет своего агента. Общая система даёт доступ к контексту, не навязывает поведение. Shared layer = библиотека, не школа.** | Centralized team agent, unified CLAUDE.md |
| D7 | Tool-agnostic shared layer | 2026-04-08 | Команда использует разные инструменты. Docs=markdown, Memory=REST API | Claude Code-only system |
| D8 | Progressive levels (0-3), each independent | 2026-04-08 | Каждый уровень ценен без предыдущих. Нет "всё или ничего" | Monolithic system, all-or-nothing |

---

## 10. Open Questions

### Ответены в v2:
- ~~Где хранить shared config?~~ → Per-project CLAUDE.md + team-knowledge repo
- ~~Единый CLAUDE.md для всех?~~ → Нет. Per-project, не per-company

### Для обсуждения с командой:
1. Какой контекст каждый объясняет заново чаще всего? (→ это идёт в CLAUDE.md)
2. Какие находки хочется переиспользовать? (→ team-knowledge repo)
3. Красные линии — что AI не должен делать? (→ конвенции)
4. Кто хочет попробовать Claude Code? Кто доволен текущим инструментом? (→ не навязываем)
5. Auto-review на PR: полезно или раздражает? (→ Phase 2 решение)
6. Что техническая команда хочет от AI больше всего? (→ приоритеты Phase 1)

---

## 11. References

### Frameworks & Tools
- [LangGraph vs AutoGen vs CrewAI Comparison (Latenode)](https://latenode.com/blog/platform-comparisons-alternatives/automation-platform-comparisons/langgraph-vs-autogen-vs-crewai-complete-ai-agent-framework-comparison-architecture-analysis-2025)
- [claude-mpm — Multi-Agent PM for Claude Code](https://github.com/bobmatnyc/claude-mpm)
- [wshobson/agents — 182 agents for Claude Code](https://github.com/wshobson/agents)
- [OpenHands (ex-OpenDevin)](https://openhands.dev/)
- [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview)

### Team Adoption
- [Claude Code Best Practices (Official)](https://code.claude.com/docs/en/best-practices)
- [Claude Code Team Setup (SmartScope)](https://smartscope.blog/en/generative-ai/claude/claude-code-creator-team-workflow-best-practices/)
- [Claude Code Enterprise Best Practices (Portkey)](https://portkey.ai/blog/claude-code-best-practices-for-enterprise-teams/)
- [Claude Code Agent Teams Setup Guide](https://claudefa.st/blog/guide/agents/agent-teams)

### Scaling Challenges
- [HBR: Scale AI Agents Like Team Members](https://hbr.org/2026/03/to-scale-ai-agents-successfully-think-of-them-like-team-members)
- [5 Production Scaling Challenges (MLMastery)](https://machinelearningmastery.com/5-production-scaling-challenges-for-agentic-ai-in-2026/)
- [State of AI Agents 2026 (Arcade)](https://www.arcade.dev/blog/5-takeaways-2026-state-of-ai-agents-claude/)
- [Snowflake: From Pilot to 6000 Users](https://www.snowflake.com/en/blog/scale-enterprise-agents/)

### Industry Adoption Frameworks
- [Swarmia: 4 Stages of AI Adoption for Engineering](https://www.swarmia.com/blog/staged-approach-AI-adoption-for-engineering/)
- [Jellyfish: AI Coding Tool Adoption Best Practices](https://jellyfish.co/blog/ai-coding-tool-adoption-best-practices/)
- [Faros AI: Enterprise Scaling Guide](https://www.faros.ai/blog/enterprise-ai-coding-assistant-adoption-scaling-guide)
- [Knostic: AI Coding Agents Deployment Playbook](https://www.knostic.ai/blog/ai-coding-agents-deployment-adoption)
- [Stanford: Enterprise AI Playbook (51 deployments)](https://digitaleconomy.stanford.edu/app/uploads/2026/03/EnterpriseAIPlaybook_PereiraGraylinBrynjolfsson.pdf)
- [Cortex: Framework for Measuring AI Adoption](https://www.cortex.io/post/a-framework-for-measuring-effective-ai-adoption-in-engineering)

### Our Experience
- [research-claude-max-efficiency.md](../research/research-claude-max-efficiency.md)
- [research-practical-claude-problems.md](../research-practical-claude-problems.md)
- [target-audience-analysis.md](target-audience-analysis.md)
- [team-survey-2026-04-08.md](team-survey-2026-04-08.md)

---

## 12. Next Actions

| Action | Owner | Due |
|--------|-------|-----|
| Review v2 plan (this doc) | Пётр | 2026-04-08 |
| Обсудить подход с командой (complement, not restrict) | Пётр | TBD |
| Написать CLAUDE.md для активных рабочих проектов | Пётр + AI | Phase 1 |
| Создать team-knowledge repo | AI | Phase 1 |
| Настроить auto-review в GitHub Actions | AI | Phase 2 |
| Расширить MCP memory для team namespace | AI | Phase 3 |
