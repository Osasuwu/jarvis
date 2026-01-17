# Jarvis — Personal AI Agent

> Персональный ИИ-агент с модульной системой инструментов и анализом capability gaps

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 О проекте

Jarvis — это модульный AI-агент для автоматизации повседневных задач с возможностью динамического подключения инструментов. Агент умеет:

- ✅ Определять доступные инструменты и использовать их для решения задач
- ✅ Выявлять отсутствие необходимых возможностей (capability gap)
- ✅ Проводить исследование: можно ли создать недостающий инструмент
- ✅ Взаимодействовать с пользователем для подтверждения критических действий (human-in-the-loop)

## 🏗️ Статус проекта

🚀 **MVP функционален** — Phase 6 (CLI & Polish) завершена

Текущие возможности:
- Модульная система инструментов (6 основных + расширяемая архитектура)
- ReAct orchestrator с поддержкой инструментов
- Groq LLM интеграция (Llama 3.3 70B)
- Human-in-the-Loop с подтверждением и аудитом (Phase 4)
- Capability Gap Analyzer для обнаружения пробелов (Phase 5)
- Красивый интерактивный CLI с Rich (Phase 6)
- Управление памятью и контекстом
- Полное покрытие тестами (79.65%, 167 unit-тестов)

см. полный план разработки в [project_vision.md](project_vision.md) и [дорожную карту](docs/roadmap.md)

## 🚀 Быстрый старт

### Требования

- Python 3.11+ (рекомендуется 3.13)
- Groq API ключ (бесплатный)

### Установка

```bash
# Клонировать репозиторий
git clone https://github.com/petrk/personal-AI-agent.git
cd personal-AI-agent

# Создать виртуальное окружение
python -m venv venv
venv\Scripts\activate  # На Windows

# Установить зависимости
pip install -e ".[dev]"

# Настроить pre-commit hooks
pre-commit install

# Создать файл конфигурации
copy .env.example .env  # На Windows
# Отредактировать .env и добавить GROQ_API_KEY
# Получить бесплатный ключ: https://console.groq.com/
```

### Использование

```bash
# Запустить агента (будет доступно после Phase 2)
jarvis "помоги мне найти все Python файлы в проекте"
```

## 📁 Структура проекта

```
personal-AI-agent/
├── src/jarvis/          # Основной код агента
│   ├── core/            # Ядро: orchestrator, planner, executor
│   ├── llm/             # Адаптеры для LLM провайдеров
│   ├── tools/           # Система инструментов
│   ├── memory/          # Управление контекстом и историей
│   ├── gap_analysis/    # Анализ capability gaps
│   └── ui/              # Пользовательский интерфейс
├── tests/               # Тесты
├── configs/             # Конфигурационные файлы
└── docs/                # Документация
```

## 🛠️ Разработка

### Запуск тестов

```bash
# Все тесты
pytest

# С покрытием
pytest --cov

# Только unit-тесты
pytest tests/unit
```

### Линтинг и форматирование

```bash
# Автоформатирование
black src tests

# Проверка линтером
ruff check src tests

# Проверка типов
mypy src
```

### Pre-commit hooks

Автоматически запускаются при каждом коммите:
- Black (форматирование)
- Ruff (линтинг)
- MyPy (проверка типов)
- Базовые проверки (trailing whitespace, yaml, etc.)

## 💡 LLM Провайдеры

Проект использует **Groq** (Llama 3.3 70B) как основной провайдер — быстро и бесплатно!

**Будущее:** Возможность использовать локальные легкие LLM (через Ollama) как дополнительные инструменты для специфичных задач.

## 📚 Документация

- [Архитектура](docs/architecture.md) — дизайн системы и компоненты
- [Vision](project_vision.md) — общее видение проекта
- [Дорожная карта](docs/roadmap.md) — план разработки

## 🤝 Вклад в проект

Проект находится на ранней стадии разработки. Contribution guidelines будут добавлены позже.

## 📄 Лицензия

MIT License — см. [LICENSE](LICENSE)

## 🎯 Roadmap

- [x] Phase 0: Подготовка репозитория
- [x] Phase 1: Core Foundation (LLM Adapter, Tool Registry)
- [x] Phase 2: Orchestrator MVP
- [x] Phase 3: Базовые инструменты (файлы, shell, веб)
- [x] Phase 4: Human-in-the-Loop (confirmations, audit, whitelist)
- [x] Phase 4: Human-in-the-Loop
- [x] Phase 5: Capability Gap Analyzer
- [x] Phase 6: CLI & Polish