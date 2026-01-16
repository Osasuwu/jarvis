# Phase 4: Human-in-the-Loop

> Система подтверждений, аудита и контроля доступа для безопасного выполнения инструментов

**Статус:** ✅ Завершено (16 января 2026)  
**Версия:** v0.4.0  
**Тесты:** 18/18 пройдено | Общее покрытие: 79.60%

---

## 📋 Обзор

Phase 4 добавляет **критический слой безопасности** в Jarvis, превращая его из автономного агента в **управляемую систему с человеческим контролем**.

Основная идея: высокорисковые операции требуют явного одобрения пользователя перед выполнением.

## 🔒 Архитектура безопасности

### 4 Основных компонента

```
┌─────────────────────────────────────────────────────┐
│           SafeExecutor (координатор)                 │
├──────────┬──────────────┬──────────────┬────────────┤
│          │              │              │            │
V          V              V              V            V
┌────┐  ┌──────┐  ┌──────────┐  ┌─────────────┐
│Tool│  │Risk  │  │Whitelist │  │AuditLogger  │
│    │  │Level │  │Manager   │  │             │
└────┘  └──────┘  └──────────┘  └─────────────┘
           │
           V
     ┌──────────────────────┐
     │Confirmation Prompt   │
     │(интерактивная)       │
     └──────────────────────┘
```

### 1. ConfirmationPrompt — Интерактивное подтверждение

**Назначение:** Запрашивать разрешение пользователя перед опасными операциями

**Класс:** `jarvis.safety.confirmation.ConfirmationPrompt`

**Основные методы:**

```python
async def request_confirmation(
    operation: str,
    tool_name: str,
    parameters: dict[str, Any],
    reason: str | None = None,
) -> bool
```

**Особенности:**
- ✅ Форматированный вывод с деталями операции
- ✅ Обработка прерываний (`KeyboardInterrupt`, `EOFError`)
- ✅ Retry логика для некорректного ввода
- ✅ Поддержка non-interactive режима

**Пример:**

```python
confirmation = ConfirmationPrompt()
approved = await confirmation.request_confirmation(
    operation="Execute shell command",
    tool_name="shell_execute",
    parameters={"command": "rm -rf /tmp/data"},
    reason="This is a HIGH risk operation"
)
if approved:
    # Execute operation
    pass
```

---

### 2. WhitelistManager — Управление разрешениями

**Назначение:** Определить какие команды и пути разрешены

**Класс:** `jarvis.safety.whitelist.WhitelistManager`

**Основные методы:**

```python
def add_command_pattern(self, pattern: str) -> None
def add_path_pattern(self, pattern: str) -> None
def is_command_allowed(self, command: str) -> bool
def is_path_allowed(self, path: str) -> bool
def save_config(self, filepath: str) -> None
def load_config(self, filepath: str) -> None
```

**Особенности:**
- ✅ Glob pattern matching (`echo *`, `src/**`)
- ✅ Forbidden patterns для блокировки опасных операций
- ✅ JSON сохранение/загрузка конфигурации
- ✅ Иерархия: forbidden > whitelist > allow all

**Примеры использования:**

```python
whitelist = WhitelistManager()

# Разрешить команды
whitelist.add_command_pattern("echo *")
whitelist.add_command_pattern("pytest *")

# Разрешить пути
whitelist.add_path_pattern("src/**")
whitelist.add_path_pattern("tests/**")

# Проверка
assert whitelist.is_command_allowed("echo hello")  # True
assert not whitelist.is_command_allowed("rm -rf /")  # False (forbidden)
assert not whitelist.is_path_allowed("etc/shadow")  # False (forbidden)
```

**Встроенные forbidden patterns:**
```python
[
    "*rm -rf*",           # Опасные удаления
    "*rm -r/*",           # Удаление от корня
    "*etc/shadow*",       # Системные файлы
    "*/../..*",           # Escape попытки
]
```

---

### 3. AuditLogger — Полное логирование

**Назначение:** Записывать все операции для отчётности и аналитики

**Класс:** `jarvis.safety.auditor.AuditLogger`

**Основные методы:**

```python
def log_operation(
    tool_name: str,
    operation: str,
    parameters: dict[str, Any],
    risk_level: str,
    user_approved: bool | None = None,
    result_status: str | None = None,
    error_message: str | None = None,
    duration_seconds: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEntry

def get_entries_by_risk(self, risk_level: str) -> list[AuditEntry]
def get_entries_by_tool(self, tool_name: str) -> list[AuditEntry]
def get_denied_operations(self) -> list[AuditEntry]
def get_failed_operations(self) -> list[AuditEntry]
def export_to_json(self, filepath: str) -> None
```

**Структура записи:**

```python
@dataclass
class AuditEntry:
    timestamp: str                    # ISO 8601
    tool_name: str                    # "shell_execute"
    operation: str                    # "Execute command"
    parameters: dict[str, Any]        # {"command": "echo hello"}
    risk_level: str                   # "HIGH", "MEDIUM", "LOW"
    user_approved: bool | None        # True/False/None
    result_status: str | None         # "success"/"failed"/"denied"
    error_message: str | None         # Если была ошибка
    duration_seconds: float | None    # Время выполнения
    metadata: dict[str, Any]          # Дополнительные данные
```

**Пример:**

```python
auditor = AuditLogger(log_file=".jarvis/audit.log")

# Логирование (автоматически вызывается SafeExecutor)
entry = auditor.log_operation(
    tool_name="shell_execute",
    operation="Execute command",
    parameters={"command": "pytest"},
    risk_level="HIGH",
    user_approved=True,
    result_status="success",
    duration_seconds=5.2
)

# Анализ
denied = auditor.get_denied_operations()
high_risk = auditor.get_entries_by_risk("HIGH")
summary = auditor.get_summary()

# Экспорт
auditor.export_to_json("audit_report.json")
```

**Вывод summary:**
```python
{
    "total_operations": 42,
    "by_risk_level": {"LOW": 30, "MEDIUM": 10, "HIGH": 2},
    "denied_count": 2,
    "failed_count": 1
}
```

---

### 4. SafeExecutor — Безопасное выполнение инструментов

**Назначение:** Скоординировать все компоненты безопасности при выполнении инструмента

**Класс:** `jarvis.safety.executor.SafeExecutor`

**Использование:**

```python
from jarvis.safety import SafeExecutor, ConfirmationPrompt, WhitelistManager, AuditLogger
from jarvis.tools.builtin import ShellExecuteTool

# Инициализация
confirmation = ConfirmationPrompt()
whitelist = WhitelistManager()
auditor = AuditLogger()

executor = SafeExecutor(
    confirmation=confirmation,
    whitelist=whitelist,
    auditor=auditor,
    require_confirmation_for=["MEDIUM", "HIGH"]
)

# Выполнение инструмента
tool = ShellExecuteTool()
result = await executor.execute(
    tool,
    command="pytest tests/"
)
```

**Flow выполнения:**

```
1. Проверка whitelist (если конфигурирован)
   └─ Если не разрешено → ValueError
   
2. Определение risk level инструмента
   
3. Если требуется подтверждение (MEDIUM/HIGH)
   └─ Запросить у пользователя
   └─ Если отклонено → denied

4. Выполнить инструмент
   └─ Поймать исключения
   
5. Залогировать в audit trail
   └─ Статус (success/failed/denied)
   └─ Время выполнения
   └─ Ошибки если были
```

---

## 🧪 Тестирование

**Файл:** `tests/unit/test_safety.py`

**18 unit-тестов:**

| Компонент | Тесты | Статус |
|-----------|-------|--------|
| ConfirmationPrompt | 3 | ✅ |
| WhitelistManager | 6 | ✅ |
| AuditLogger | 5 | ✅ |
| SafeExecutor | 4 | ✅ |

**Примеры тестов:**

```python
# Подтверждение отклонено
async def test_confirmation_request_denied():
    confirmation = ConfirmationPrompt()
    with patch("builtins.input", return_value="no"):
        result = await confirmation.request_confirmation(...)
        assert result is False

# Whitelist блокирует опасные команды
def test_whitelist_forbidden_patterns():
    wl = WhitelistManager()
    assert not wl.is_command_allowed("rm -rf *")
    assert not wl.is_path_allowed("etc/shadow")

# Аудит регистрирует все операции
def test_audit_logger_summary():
    auditor = AuditLogger()
    auditor.log_operation(...)
    summary = auditor.get_summary()
    assert summary["total_operations"] == 1
```

---

## 🔐 Risk Level Classification

Phase 3 инструменты уже имели risk level, Phase 4 теперь их использует:

| Инструмент | Risk Level | Требует подтверждение | Описание |
|-----------|-----------|----------------------|----------|
| `file_read` | LOW | ❌ | Только чтение |
| `file_write` | MEDIUM | ✅ | Модификация FS |
| `list_directory` | LOW | ❌ | Только просмотр |
| `shell_execute` | HIGH | ✅ | Произвольные команды |
| `web_fetch` | LOW | ❌ | Только GET |
| `web_search` | LOW | ❌ | Только поиск |

---

## 📊 Метрики

| Метрика | Значение | Статус |
|---------|----------|--------|
| Компонентов реализовано | 4/4 | ✅ |
| Unit-тестов | 18 | ✅ |
| Тестов пройдено | 18/18 | ✅ |
| Покрытие Phase 4 | 70.18% (executor) | ✅ |
| Общее покрытие | 79.60% | ✅ |
| Строк кода | ~218 | ✅ |
| Строк тестов | ~370 | ✅ |

---

## 💾 Примеры использования

### Пример 1: Базовое использование с confirmations

```python
from jarvis.safety import SafeExecutor, ConfirmationPrompt, AuditLogger

auditor = AuditLogger(log_file=".jarvis/audit.log")
confirmation = ConfirmationPrompt()
executor = SafeExecutor(confirmation=confirmation, auditor=auditor)

# Выполнение HIGH-risk инструмента
# Пользователю будет предложено подтверждение
result = await executor.execute(shell_tool, command="python setup.py install")
```

### Пример 2: Whitelist для автоматизации

```python
whitelist = WhitelistManager()
whitelist.add_command_pattern("pytest *")
whitelist.add_command_pattern("python -m myapp *")
whitelist.add_path_pattern("src/**")
whitelist.add_path_pattern("tests/**")
whitelist.save_config(".jarvis/whitelist.json")

# Теперь безопасно выполнять без подтверждений
executor = SafeExecutor(whitelist=whitelist)
result = await executor.execute(shell_tool, command="pytest tests/")  # OK
result = await executor.execute(shell_tool, command="rm -rf /")      # ValueError!
```

### Пример 3: Audit анализ

```python
auditor = AuditLogger()

# Выполнить несколько операций...

# Анализ
print(auditor.get_summary())
# {
#     "total_operations": 10,
#     "by_risk_level": {"LOW": 8, "MEDIUM": 1, "HIGH": 1},
#     "denied_count": 1,
#     "failed_count": 0
# }

# Экспорт для отчёта
auditor.export_to_json("security_audit.json")
```

---

## 🚀 Интеграция с Orchestrator

В будущих версиях `SafeExecutor` будет интегрирован в `Orchestrator`:

```python
# Вместо
result = await tool.execute(**params)

# Будет
executor = SafeExecutor(confirmation=..., whitelist=..., auditor=...)
result = await executor.execute(tool, **params)
```

---

## 🎯 Критерии готовности (Phase 4)

- [x] **Опасные операции требуют подтверждения**
  - ConfirmationPrompt реализован ✅
  - SafeExecutor проверяет risk level ✅
  - MEDIUM/HIGH требуют подтверждения ✅

- [x] **Все действия логируются**
  - AuditLogger полностью функционален ✅
  - JSON экспорт реализован ✅
  - Фильтрация и анализ работают ✅

- [x] **Пользователь может видеть, что будет выполнено**
  - Confirmation prompt показывает детали ✅
  - Audit log хранит всю историю ✅
  - Summary и отчёты доступны ✅

---

## 📚 Ссылки

- [Safety Module](../src/jarvis/safety/) — исходный код
- [Tests](../tests/unit/test_safety.py) — unit-тесты
- [Architecture](architecture.md) — архитектура системы

---

**Дата завершения:** 16 января 2026  
**Версия:** v0.4.0  
**Статус:** ✅ READY FOR PRODUCTION
