# Архитектура Jarvis AI Agent

> Документ описывает архитектуру персонального AI-агента с модульной системой инструментов

**Версия:** 0.1.0  
**Дата:** Январь 2026  
**Статус:** Draft (MVP Design)

---

## Содержание

1. [Обзор](#обзор)
2. [Архитектурные принципы](#архитектурные-принципы)
3. [Компоненты системы](#компоненты-системы)
4. [Потоки данных](#потоки-данных)
5. [Tool System](#tool-system)
6. [Capability Gap Analysis](#capability-gap-analysis)
7. [Технические решения](#технические-решения)

---

## Обзор

Jarvis — это autonomous AI agent, построенный на паттерне **ReAct** (Reasoning + Acting). Агент принимает задачу от пользователя, декомпозирует её на шаги, выбирает инструменты для выполнения и взаимодействует с пользователем для подтверждения критических операций.

### Ключевые возможности

- **Модульность:** инструменты подключаются динамически
- **Масштабируемость:** простое добавление новых capabilities
- **Human-in-the-Loop:** контроль пользователя над опасными операциями
- **Self-awareness:** агент знает, что он может и не может делать
- **Research capability:** поиск решений для недостающих инструментов

---

## Архитектурные принципы

### 1. Separation of Concerns
Каждый компонент имеет четко определенную ответственность

### 2. Plugin Architecture
Инструменты — это плагины с единым интерфейсом

### 3. LLM-Agnostic
Абстракция над LLM провайдерами (OpenAI, Anthropic, local models)

### 4. Safety First
Опасные операции требуют явного подтверждения пользователя

### 5. Observability
Подробное логирование каждого шага для отладки

---

## Компоненты системы

```
┌──────────────────────────────────────────────────────────────┐
│                     USER INTERFACE LAYER                     │
│                                                              │
│  ┌─────────────┐         ┌─────────────┐                   │
│  │     CLI     │         │   Web UI    │  (Future)          │
│  └─────────────┘         └─────────────┘                   │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR (Core)                      │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Task Parser  │→ │   Planner    │→ │ Execution Engine │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│         ↓                  ↓                    ↓            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ LLM Adapter  │  │   Memory     │  │ Human Approval   │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                     TOOL REGISTRY                            │
│                                                              │
│  Tool Manifest: {name, description, parameters, schema}      │
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ File Ops │ │ Browser  │ │  Shell   │ │ Custom Tools │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                CAPABILITY GAP ANALYZER                       │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Gap Detector │→ │  Researcher  │→ │ Tool Proposer    │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Описание компонентов

#### 1. User Interface Layer
- **CLI:** Основной интерфейс для MVP (Typer + Rich)
- **Web UI:** Будущее расширение (FastAPI + React)

#### 2. Orchestrator
Центральный компонент агента

**Task Parser**
- Парсит пользовательский запрос
- Извлекает intent и entities
- Определяет тип задачи

**Planner**
- Проверяет доступные инструменты
- Составляет план выполнения
- Декомпозирует сложные задачи

**Execution Engine**
- Выполняет план пошагово
- Обрабатывает результаты
- Управляет ошибками

**LLM Adapter**
- Абстракция над LLM провайдерами
- Поддержка function calling
- Управление контекстом

**Memory**
- История диалога
- Контекст выполнения
- Результаты предыдущих операций

**Human Approval**
- Запрос подтверждений
- Оценка риска операции
- Логирование решений

#### 3. Tool Registry
Централизованное хранилище инструментов

- **Discovery:** поиск инструментов по capability
- **Validation:** проверка параметров
- **Execution:** вызов инструментов
- **Metadata:** описания для LLM

#### 4. Capability Gap Analyzer
Система обнаружения и восполнения пробелов

**Gap Detector**
- Определяет, когда инструмента недостаточно
- Анализирует неудачные попытки

**Researcher**
- Поиск в интернете (API, библиотеки)
- Анализ системных возможностей
- Оценка сложности реализации

**Tool Proposer**
- Генерация предложения инструмента
- Спецификация интерфейса
- Примеры использования

---

## Потоки данных

### Main Execution Flow

```
1. User Input
   ↓
2. Task Parser → Intent Recognition
   ↓
3. Planner → Tool Discovery
   ├─→ Tools Found → Create Plan
   └─→ Tools Missing → Gap Analysis Flow
   ↓
4. Execution Engine → Execute Step by Step
   ├─→ High Risk? → Human Approval
   └─→ Execute Tool
   ↓
5. Collect Results
   ↓
6. Format & Return Response
```

### Capability Gap Flow

```
1. Gap Detected (no suitable tool)
   ↓
2. Gap Detector → Analyze requirement
   ↓
3. Researcher
   ├─→ Search Internet (APIs, libraries)
   ├─→ Check System Capabilities
   └─→ Estimate Implementation Effort
   ↓
4. Tool Proposer → Generate Proposal
   ↓
5. Human Review
   ├─→ Approved → (Future) Generate Tool
   └─→ Rejected → Log & Inform User
```

---

## Tool System

### Tool Interface

Каждый инструмент реализует следующий контракт:

```python
class Tool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema
    returns: dict     # JSON Schema
    requires_confirmation: bool
    risk_level: RiskLevel  # LOW, MEDIUM, HIGH
    capabilities: list[str]
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        pass
    
    def to_llm_schema(self) -> dict:
        """Преобразование в схему для LLM function calling"""
        pass
```

### Tool Categories

| Категория | Примеры | Risk Level |
|-----------|---------|------------|
| **File Operations** | read_file, write_file, list_dir | MEDIUM |
| **Shell** | execute_command | HIGH |
| **Web** | search_web, fetch_url | LOW |
| **System** | get_env, set_env | MEDIUM |
| **Custom** | user-defined | VARIABLE |

### Tool Registry Structure

```python
{
  "file_read": {
    "name": "file_read",
    "description": "Read contents of a file",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "File path"}
      },
      "required": ["path"]
    },
    "requires_confirmation": false,
    "risk_level": "LOW",
    "capabilities": ["filesystem", "read"]
  }
}
```

---

## Capability Gap Analysis

### Gap Detection Triggers

1. **Explicit:** агент не находит подходящий инструмент
2. **Implicit:** пользователь запрашивает неподдерживаемую операцию
3. **Pattern-based:** повторяющиеся неудачные попытки

### Research Strategy

1. **Web Search:** поиск готовых решений (библиотеки, API)
2. **System Analysis:** проверка возможностей ОС
3. **Feasibility Check:** оценка сложности реализации

### Tool Proposal Format

```yaml
proposed_tool:
  name: "screenshot_capture"
  reason: "User requested taking a screenshot"
  implementation:
    approach: "Use pillow + platform-specific APIs"
    libraries: ["pillow", "pyautogui"]
    complexity: "LOW"
  interface:
    parameters:
      region: "optional, specific area"
      output_path: "where to save"
    returns:
      success: boolean
      path: string
  requires_approval: true
```

---

## Технические решения

### Конфигурация

- **Format:** YAML + Environment Variables
- **Hierarchy:** defaults < user config < env vars
- **Validation:** Pydantic Settings

### Логирование

- **Library:** structlog
- **Levels:** DEBUG, INFO, WARNING, ERROR
- **Output:** Console + File (rotating)

### Хранилище

**MVP:**
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
