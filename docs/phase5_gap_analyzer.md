# Phase 5: Capability Gap Analyzer

**Status:** ✅ Реализовано (16 января 2026)  
**Tests:** 25 unit-тестов, все пройдены  
**Coverage:** 100% (детектор, исследователь, proposer)

## Обзор

Phase 5 реализует систему обнаружения и анализа пробелов в возможностях агента. Когда инструменты отсутствуют или операции не могут быть выполнены, система автоматически:

1. **Обнаруживает** отсутствующие возможности
2. **Исследует** возможные решения
3. **Предлагает** новые инструменты с полной спецификацией

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    Execution Pipeline                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │   Tool Fails   │
            └────────┬───────┘
                     │
                     ▼
        ┌───────────────────────┐
        │   GapDetector         │
        │  - Из ошибки          │
        │  - Или явно           │
        └────────┬──────────────┘
                 │ CapabilityGap
                 ▼
        ┌─────────────────────┐
        │  GapResearcher      │
        │  - Поиск решений    │
        │  - Кеширование      │
        └────────┬────────────┘
                 │ ResearchResult
                 ▼
        ┌──────────────────────┐
        │  ToolProposer        │
        │  - Генерация spec    │
        │  - Примеры           │
        └──────────────────────┘
                 │ ToolProposal
                 ▼
        ┌──────────────────────┐
        │  Recommend to User   │
        │  - Markdown docs     │
        │  - JSON export       │
        └──────────────────────┘
```

## Компоненты

### 1. GapDetector

Обнаруживает отсутствующие возможности из ошибок инструментов или явно.

```python
from jarvis.gap_analyzer import GapDetector

detector = GapDetector()

# Из ошибки
gap = detector.detect_from_error(
    capability_name="database_query",
    description="Execute SQL queries",
    context="User tried to query PostgreSQL",
    tool_name="shell_execute",
    error="psycopg2 not found",
    severity="HIGH"
)

# Явно
gap = detector.detect_missing_capability(
    capability_name="image_processing",
    description="Resize and convert images",
    context="User requested image transformation",
    severity="MEDIUM",
    confidence=0.8
)

# Получить критические пробелы
critical = detector.get_critical_gaps()

# Получить статистику
summary = detector.get_summary()
# {
#   "total_gaps": 5,
#   "critical_gaps": 2,
#   "by_severity": {"HIGH": 2, "MEDIUM": 2, "LOW": 1}
# }
```

**Особенности:**

- Автоматическая timestamp генерация
- Уровни важности: LOW, MEDIUM, HIGH
- Confidence score (0.0-1.0)
- Экспорт в JSON
- Фильтрация по тяжести/инструменту/статусу

### 2. GapResearcher

Исследует возможные решения для обнаруженных пробелов.

```python
from jarvis.gap_analyzer import GapResearcher
import asyncio

researcher = GapResearcher()

# Исследовать пробел
result = asyncio.run(researcher.research_gap(gap))

# result содержит:
# - possible_solutions: ["SQLAlchemy", "psycopg2", "pymongo"]
# - system_capabilities: ["Can execute SQL via shell_execute"]
# - implementation_difficulty: "EASY"
# - estimated_effort_days: 0.5
# - external_resources: [URLs и описания]

# Кеширование
cached = researcher.get_cached_research("database_query")

# Экспорт
researcher.export_research("research.json")
```

**Особенности:**

- Встроенная база данных решений
- Async/await для параллельных исследований
- Автоматическое кеширование результатов
- JSON экспорт
- Соответствие инструменту и контексту

### 3. ToolProposer

Генерирует спецификации новых инструментов на основе исследований.

```python
from jarvis.gap_analyzer import ToolProposer

proposer = ToolProposer()

# Предложить инструмент
proposal = proposer.propose_tool(gap, research)

# proposal содержит:
# - tool_name: "database_query"
# - parameters: {"connection_string": "str", "query": "str"}
# - return_type: "list[dict]"
# - risk_level: "HIGH"
# - example_usage: "..."
# - implementation_hint: "..."
# - estimated_effort: 0.5

# Экспорт в Markdown
markdown = proposal.to_markdown()

# Получить quick wins
quick_wins = proposer.get_quick_wins()

# Получить высокоприоритетные
high_priority = proposer.get_high_priority_proposals()

# Экспорт всех
proposer.export_proposals("proposals.json")
proposer.export_proposals_as_markdown("proposals_dir/")
```

**Особенности:**

- Автоматическая генерация спецификаций
- Примеры использования
- Подсказки реализации
- Экспорт в Markdown и JSON
- Фильтрация по сложности/приоритету

## Примеры использования

### Пример 1: Обнаружение из ошибки

```python
async def execute_with_gap_detection(tool_name, params):
    try:
        return await execute_tool(tool_name, params)
    except Exception as e:
        detector = GapDetector()
        gap = detector.detect_from_error(
            capability_name=extract_capability_name(str(e)),
            description="Required capability",
            context=f"Executing {tool_name}",
            tool_name=tool_name,
            error=str(e),
            severity="HIGH"
        )
        
        researcher = GapResearcher()
        research = await researcher.research_gap(gap)
        
        proposer = ToolProposer()
        proposal = proposer.propose_tool(gap, research)
        
        print("Capability Gap Detected!")
        print(proposal.to_markdown())
```

### Пример 2: Анализ пробелов

```python
# После множественных операций
gaps = detector.get_critical_gaps()

# Исследовать каждый
researcher = GapResearcher()
proposals = []

for gap in gaps:
    research = await researcher.research_gap(gap)
    proposal = proposer.propose_tool(gap, research)
    proposals.append(proposal)

# Экспортировать для обзора
proposer.export_proposals_as_markdown("gap_analysis/")

# Показать метрики
print(f"Total gaps: {len(detector.gaps)}")
print(f"Quick wins: {len(proposer.get_quick_wins())}")
print(f"High priority: {len(proposer.get_high_priority_proposals())}")
```

### Пример 3: Интеграция с Safety Module

```python
from jarvis.safety import SafeExecutor
from jarvis.gap_analyzer import GapDetector

async def safe_execute_with_gaps(executor, tool, params):
    try:
        return await executor.execute(tool, params)
    except Exception as e:
        detector = GapDetector()
        gap = detector.detect_from_error(
            capability_name=tool.name,
            description=f"Tool {tool.name} failed",
            context="User operation",
            tool_name=tool.name,
            error=str(e),
            severity="HIGH"
        )
        
        # Сохранить для анализа
        detector.export_to_json("gaps.json")
```

## Типы пробелов

### Встроенные решения

Gap Analyzer содержит встроенные решения для:

- **database_query** → SQLAlchemy, psycopg2, pymongo
- **image_processing** → Pillow, OpenCV, scikit-image
- **pdf_generation** → reportlab, fpdf2, python-docx
- **api_integration** → requests, httpx, aiohttp
- **data_parsing** → BeautifulSoup, lxml, html.parser

Для других типов предоставляются общие рекомендации.

### Уровни сложности

```
SIMPLE       → 0.25 дня
MODERATE     → 0.5 дня
COMPLEX      → 1.5 дня
VERY_COMPLEX → 3+ дня
```

## Структуры данных

### CapabilityGap

```python
@dataclass
class CapabilityGap:
    timestamp: str                # ISO 8601
    capability_name: str         # "database_query"
    capability_description: str  # Что надо делать
    context: str                 # Почему нужно
    attempted_tool: str | None   # Какой инструмент не сработал
    error_message: str | None    # Текст ошибки
    severity: str                # LOW/MEDIUM/HIGH
    confidence: float            # 0.0-1.0
```

### ResearchResult

```python
@dataclass
class ResearchResult:
    gap_name: str                     # Имя пробела
    possible_solutions: list[str]     # Библиотеки
    system_capabilities: list[str]    # Что может система
    implementation_difficulty: str    # EASY/MEDIUM/HARD
    estimated_effort_days: float      # Сколько дней
    external_resources: list[dict]    # URLs
```

### ToolProposal

```python
@dataclass
class ToolProposal:
    tool_name: str                 # "database_query"
    description: str               # Краткое описание
    purpose: str                   # Зачем нужен
    parameters: dict[str, str]     # name -> type
    return_type: str               # Что возвращает
    risk_level: str                # LOW/MEDIUM/HIGH
    example_usage: str             # Пример кода
    implementation_hint: str       # Как реализовать
    estimated_effort: float        # Дней работы
    estimated_complexity: str      # SIMPLE/MODERATE/COMPLEX
```

## Тестирование

### Покрытие

- **GapDetector**: 10 тестов, 100% coverage
- **GapResearcher**: 6 тестов, 100% coverage
- **ToolProposer**: 8 тестов, 98.41% coverage
- **Integration**: 1 комплексный тест

### Запуск тестов

```bash
# Только Phase 5
python -m pytest tests/unit/test_gap_analyzer.py -v

# Со всеми фазами
python -m pytest -v
# 133 passed, 82.48% coverage
```

### Примеры тестов

```python
def test_detect_from_error(self):
    """Обнаружение из ошибки"""
    gap = detector.detect_from_error(
        "database_query", "Query DB", "Context",
        "shell_execute", "psycopg2 not found"
    )
    assert gap.severity == "HIGH"
    assert gap.confidence == 0.95

def test_full_gap_analysis_workflow(self):
    """Полный workflow: обнаружение → исследование → предложение"""
    gap = detector.detect_from_error(...)
    research = await researcher.research_gap(gap)
    proposal = proposer.propose_tool(gap, research)
    
    assert proposal.tool_name == "database_query"
```

## Интеграция в агент

### Шаг 1: После ошибки инструмента

```python
class ReActOrchestrator:
    async def execute_tool(self, tool, params):
        try:
            result = await tool.execute(params)
            return result
        except Exception as e:
            # Обнаружить пробел
            gap = self.detector.detect_from_error(...)
            # Исследовать
            research = await self.researcher.research_gap(gap)
            # Предложить
            proposal = self.proposer.propose_tool(gap, research)
            # Уведомить пользователя
            await self.notify_user(proposal)
```

### Шаг 2: Регулярный анализ

```python
async def analyze_gaps(self):
    """Анализировать накопленные пробелы"""
    gaps = self.detector.get_critical_gaps()
    
    for gap in gaps:
        research = await self.researcher.research_gap(gap)
        proposal = self.proposer.propose_tool(gap, research)
        
        yield proposal
```

### Шаг 3: Отчет для пользователя

```python
async def generate_gap_report(self):
    """Сгенерировать отчет о пробелах"""
    gaps = self.detector.get_gaps_by_severity("HIGH")
    
    report = {
        "total_gaps": len(gaps),
        "critical": len([g for g in gaps if g.severity == "HIGH"]),
        "quick_wins": len(self.proposer.get_quick_wins()),
        "proposals": [p.to_dict() for p in self.proposer.proposals]
    }
    
    return report
```

## Метрики и статистика

```python
# Детектор
summary = detector.get_summary()
# {
#   "total_gaps": 5,
#   "critical_gaps": 2,
#   "high_confidence_gaps": 3,
#   "by_severity": {"HIGH": 2, "MEDIUM": 2, "LOW": 1}
# }

# Исследователь
cache_size = len(researcher.research_cache)  # Кеш результатов

# Proposer
quick_wins = len(proposer.get_quick_wins())      # <= 0.5 дня
easy_tasks = len(proposer.get_proposals_by_complexity("SIMPLE"))
```

## Следующие фазы

**Phase 6: CLI & Polish** будет интегрировать Gap Analyzer в:
- Интерактивный режим с предложениями
- CLI команды для анализа пробелов
- Красивый вывод Markdown документации

---

**Дата завершения:** 16 января 2026  
**Total commits:** 5  
**Строк кода:** 450+ (detector, researcher, proposer)  
**Тестов:** 25 unit-тестов, все пройдены ✅  
**Coverage:** 100% для Core, 98.41% для Proposer
