# Phase 6: CLI & Polish

**Status:** ✅ Реализовано (16 января 2026)
**Tests:** 34 unit-тестов, все пройдены
**Coverage:** CLI модуль 75.82% (formatter), 84.31% (history), 48.42% (interface)

## Обзор

Phase 6 реализует красивый интерактивный CLI для Jarvis агента с использованием Rich library. Система включает:

1. **OutputFormatter** — красивый вывод с цветами и таблицами
2. **CommandHistory** — сохранение и поиск истории команд
3. **CLIInterface** — интерактивный командный интерфейс

## Архитектура

```
┌────────────────────────────────────┐
│    Jarvis CLI Interface            │
├────────────────────────────────────┤
│  CLIInterface                      │
│  ├─ OutputFormatter (Rich)         │
│  ├─ CommandHistory                 │
│  └─ Command Registration           │
├────────────────────────────────────┤
│  Built-in Commands                 │
│  ├─ help       - Show commands     │
│  ├─ history    - Show history      │
│  ├─ clear      - Clear screen      │
│  ├─ stats      - Show statistics   │
│  └─ exit       - Exit application  │
└────────────────────────────────────┘
```

## Компоненты

### 1. OutputFormatter

Форматирует вывод с Rich library для красивого отображения.

```python
from jarvis.cli import OutputFormatter

formatter = OutputFormatter()

# Различные форматы вывода
formatter.print_header("Title", "Subtitle")
formatter.print_success("Operation completed")
formatter.print_error("Something went wrong")
formatter.print_warning("Be careful")
formatter.print_info("Information")

# Таблицы
data = [
    {"name": "Alice", "age": 30},
    {"name": "Bob", "age": 25}
]
formatter.print_table(data, title="Users")

# JSON
formatter.print_json({"key": "value", "count": 42})

# Код с подсветкой
formatter.print_code('print("hello")', language="python")

# Списки
formatter.print_list(["Item 1", "Item 2", "Item 3"], title="Items")

# Словари
formatter.print_dict({"setting1": "value1", "setting2": 123})

# Интерактивный ввод
value = formatter.input_prompt("Enter value", default="default_value")

# Подтверждение
if formatter.confirm("Are you sure?", default=True):
    print("Confirmed")
```

**Особенности:**

- Rich-based rendering (цвета, таблицы, панели)
- Поддержка кодов с синтаксис-хайлайтингом
- JSON форматирование
- Таблицы с автоматическим выравниванием
- Интерактивные подсказки и подтверждения
- Иерархические структуры (trees)

### 2. CommandHistory

Сохраняет и управляет историей команд.

```python
from jarvis.cli import CommandHistory
import asyncio

history = CommandHistory()  # ~/.jarvis/history.json

# Добавить команду
history.add_command("list files", status="success", result="10 files")
history.add_command("query db", status="error", error="Connection timeout")

# Получить историю
recent = history.get_recent(limit=10)
successful = history.get_successful_commands()
failed = history.get_failed_commands()

# Поиск
results = history.search("list")

# Статистика
summary = history.get_summary()
# {
#   "total_commands": 100,
#   "successful": 95,
#   "failed": 5,
#   "success_rate": 95.0
# }

# Экспорт
history.export_to_json("history.json")

# Очистка
history.clear_history()
```

**Особенности:**

- JSON-based persistence (~/.jarvis/history.json)
- Timestamp для каждой команды
- Фильтрация по статусу (success/error/cancelled)
- Поиск по тексту команды
- Статистика успеха/ошибок
- Экспорт для анализа

### 3. CLIInterface

Интерактивный командный интерфейс с поддержкой custom команд.

```python
from jarvis.cli import CLIInterface
import asyncio

# Создать CLI
cli = CLIInterface()

# Зарегистрировать custom команду
def echo_handler(args):
    return f"Echo: {args}"

cli.register_command("echo", echo_handler, "Echo text")

# Async команда
async def async_handler(args):
    await asyncio.sleep(1)
    return f"Result: {args}"

cli.register_command("async_cmd", async_handler, "Async command")

# Запустить интерактивный режим
asyncio.run(cli.start_interactive_mode())

# Или выполнить одну команду
result = asyncio.run(cli.run_command("echo hello"))
```

**Built-in команды:**

```
help          - Show available commands
history       - Show command history
  history clear    - Clear all history
  history export   - Export history to file
clear         - Clear screen
stats         - Show statistics
exit          - Exit application
```

**Особенности:**

- Интерактивный REPL loop
- Async/sync command support
- Command registration system
- Error handling и retry logic
- KeyboardInterrupt (Ctrl+C) support
- Встроенная история команд
- Command-level logging

## Примеры использования

### Пример 1: Простой CLI с custom командами

```python
from jarvis.cli import CLIInterface, OutputFormatter
import asyncio

async def main():
    formatter = OutputFormatter()
    cli = CLIInterface(formatter)

    # Регистрировать команды
    def list_handler(args):
        items = ["Item 1", "Item 2", "Item 3"]
        formatter.print_list(items, title="Items")

    def config_handler(args):
        config = {"debug": True, "timeout": 30}
        formatter.print_dict(config, title="Configuration")

    cli.register_command("list", list_handler, "List items")
    cli.register_command("config", config_handler, "Show config")

    # Запустить интерактивный режим
    await cli.start_interactive_mode()

asyncio.run(main())
```

### Пример 2: Интеграция с Jarvis агентом

```python
from jarvis.cli import CLIInterface, OutputFormatter
from jarvis.core import ReActOrchestrator
import asyncio

class JarvisCLI(CLIInterface):
    def __init__(self, orchestrator):
        super().__init__()
        self.orchestrator = orchestrator

        # Регистрировать команды агента
        self.register_command(
            "ask",
            self._ask_handler,
            "Ask Jarvis to do something"
        )
        self.register_command(
            "tools",
            self._tools_handler,
            "Show available tools"
        )

    async def _ask_handler(self, args):
        if not args:
            self.formatter.print_warning("Please provide a task")
            return

        self.formatter.print_info(f"Processing: {args}")
        result = await self.orchestrator.execute(args)
        self.formatter.print_success(f"Completed: {result}")

    def _tools_handler(self, args):
        tools = self.orchestrator.get_available_tools()
        self.formatter.print_list(tools, title="Available Tools")

# Использование
orchestrator = ReActOrchestrator()
cli = JarvisCLI(orchestrator)
asyncio.run(cli.start_interactive_mode())
```

### Пример 3: История команд

```python
from jarvis.cli import CommandHistory, OutputFormatter

# Создать историю
history = CommandHistory()

# Добавить несколько команд
for i in range(5):
    history.add_command(
        f"operation {i}",
        status="success" if i % 2 == 0 else "error",
        result=f"Result {i}" if i % 2 == 0 else "",
        error=f"Error {i}" if i % 2 != 0 else ""
    )

# Показать статистику
formatter = OutputFormatter()
summary = history.get_summary()
formatter.print_dict(summary, title="History Statistics")

# Показать последние
recent = history.get_recent(limit=3)
formatter.print_table(recent, title="Recent Commands", columns=["command", "status"])

# Поиск
results = history.search("operation 2")
print(f"Found {len(results)} commands")

# Экспорт
history.export_to_json("cli_history.json")
```

## Тестирование

### Покрытие

- **OutputFormatter**: 15 тестов, 75.82% coverage
- **CommandHistory**: 10 тестов, 84.31% coverage
- **CLIInterface**: 8 тестов, 48.42% coverage
- **Integration**: 1 комплексный тест

### Запуск тестов

```bash
# Только Phase 6
python -m pytest tests/unit/test_cli.py -v

# Все тесты
python -m pytest
# 167 passed, 79.65% coverage
```

### Примеры тестов

```python
def test_output_formatter_table():
    """Test table formatting."""
    formatter = OutputFormatter()
    data = [{"name": "Alice", "age": 30}]
    formatter.print_table(data)  # No exception

def test_command_history_add():
    """Test adding command."""
    history = CommandHistory()
    history.add_command("test", status="success")
    assert len(history.commands) == 1

def test_cli_register_command():
    """Test command registration."""
    cli = CLIInterface()
    cli.register_command("test", lambda x: "result")
    assert "test" in cli.get_commands()

async def test_cli_run_command():
    """Test running command."""
    cli = CLIInterface()
    cli.register_command("echo", lambda x: f"Echo: {x}")
    result = await cli.run_command("echo hello")
    assert result is not None
```

## Интеграция в агент

### Шаг 1: Создать CLI для агента

```python
from jarvis.cli import CLIInterface
from jarvis.core import ReActOrchestrator

class JarvisCLI(CLIInterface):
    def __init__(self, orchestrator):
        super().__init__()
        self.orchestrator = orchestrator
        self._setup_jarvis_commands()

    def _setup_jarvis_commands(self):
        self.register_command(
            "ask",
            self._ask,
            "Ask Jarvis to do something"
        )
```

### Шаг 2: Интегрировать safety и gap analyzer

```python
class JarvisCLI(CLIInterface):
    async def _ask(self, args):
        try:
            result = await self.orchestrator.execute(args)
            self.formatter.print_success(result)
        except Exception as e:
            # Gap detected - show proposal
            gap_proposal = await self.gap_analyzer.propose_solution(e)
            self.formatter.print_panel(
                gap_proposal.to_markdown(),
                title="Capability Gap Detected"
            )
```

### Шаг 3: Запустить интерактивный режим

```python
import asyncio

async def main():
    orchestrator = ReActOrchestrator()
    cli = JarvisCLI(orchestrator)
    await cli.start_interactive_mode()

if __name__ == "__main__":
    asyncio.run(main())
```

## Rich Library Features

CLI использует Rich library для:

- **Таблицы** с красивым форматированием
- **Панели** для выделения важной информации
- **Синтаксис-хайлайтинг** кода
- **Цвета и стили** для улучшения читаемости
- **Прогресс-бары** для долгих операций
- **Иерархические структуры** (trees)
- **Markdown** поддержка в панелях

## История команд

История хранится в `~/.jarvis/history.json`:

```json
[
  {
    "timestamp": "2026-01-16T10:30:00.123456",
    "command": "ask list my files",
    "status": "success",
    "result": "3 files found",
    "error": ""
  },
  {
    "timestamp": "2026-01-16T10:31:00.654321",
    "command": "ask query database",
    "status": "error",
    "result": "",
    "error": "Connection timeout"
  }
]
```

## Метрики и статистика

```python
# Получить метрики
summary = history.get_summary()
print(f"Total: {summary['total_commands']}")
print(f"Success: {summary['successful']} ({summary['success_rate']:.1f}%)")
print(f"Failed: {summary['failed']}")

# Экспортировать для анализа
history.export_to_json("analysis.json")
```

## Следующие фазы

**Phase 7: Advanced Memory** будет использовать CLI для:
- Сохранения user preferences
- Управления долгосрочной памятью
- Персонализированных ответов

---

**Дата завершения:** 16 января 2026
**Total commits:** 2
**Строк кода:** 470+ (formatter, history, interface)
**Тестов:** 34 unit-тестов, все пройдены ✅
**Coverage:** 75.82% formatter, 84.31% history, 48.42% interface
**Full suite:** 167 тестов, 79.65% coverage
