# LLM Providers Guide

## Текущая конфигурация

Jarvis использует **Groq** (Llama 3.3 70B) как основной LLM провайдер для рассуждения и планирования.

## Архитектура провайдеров

```
Main LLM (Groq)           →  Orchestrator, Planner, Gap Analysis
   ↓
Specialized Tools         →  Локальные LLM для специфичных задач
   ├─ Text Summarization  →  Ollama (llama3.2 или phi-3)
   ├─ Code Analysis       →  Ollama (codellama)
   └─ Embeddings          →  Ollama (nomic-embed-text)
```

## Основной провайдер: Groq

### Почему Groq?

- ✅ **Бесплатный** generous tier (100 запросов/минуту)
- ✅ **Быстрый** — самая высокая скорость inference
- ✅ **Качественный** — Llama 3.3 70B сравним с GPT-4
- ✅ **Простой API** — совместим с OpenAI SDK

### Настройка

```bash
# 1. Получить ключ: https://console.groq.com/
# 2. Добавить в .env
GROQ_API_KEY=gsk_...

# 3. Настроить модель (опционально)
GROQ_MODEL=llama-3.3-70b-versatile  # дефолт
# или
GROQ_MODEL=llama-3.1-70b-versatile
# или
GROQ_MODEL=mixtral-8x7b-32768
```

### Ограничения free tier

- **Скорость:** 100 запросов/минуту (более чем достаточно)
- **Токены:** ~30K запросов/месяц
- **Context:** до 32K токенов

## Локальные LLM как инструменты (Future)

### Концепция

Вместо того чтобы запускать тяжелую локальную LLM для всего агента, используем **легкие специализированные модели** как отдельные инструменты:

```python
# Пример использования в Phase 3+
@tool("summarize_text")
async def summarize_with_local_llm(text: str) -> str:
    """
    Использует локальную Ollama (phi-3) для суммаризации.
    Groq используется для планирования, Ollama — для исполнения.
    """
    # TODO: Phase 3 implementation
    pass
```

### Преимущества подхода

| Аспект | Groq (главный) | Ollama (инструмент) |
|--------|----------------|---------------------|
| Скорость | ⚡ Очень быстро | 🐌 Медленнее |
| Использование | Рассуждение, планирование | Специфичные задачи |
| Нагрузка | Облако | Локально |
| Стоимость | Free tier | 100% бесплатно |

### Рекомендуемые легкие модели

#### Для суммаризации текста
```bash
ollama pull phi-3:mini        # ~2GB, быстро
ollama pull llama3.2:3b       # ~2GB, качественно
```

#### Для анализа кода
```bash
ollama pull codellama:7b      # ~4GB, специализировано
```

#### Для embeddings
```bash
ollama pull nomic-embed-text  # ~274MB, очень легко
```

## Миграция между провайдерами

### Абстракция LLM Adapter (Phase 1)

Все провайдеры реализуют единый интерфейс:

```python
class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self, 
        messages: list[dict],
        tools: list[Tool] = None,
        **kwargs
    ) -> LLMResponse:
        pass
```

### Поддерживаемые провайдеры (в будущем)

- [x] **Groq** (Phase 1)
- [ ] **Ollama** (Phase 3, как инструмент)
- [ ] **Gemini** (Phase 4+, альтернатива)
- [ ] **OpenAI** (Phase 4+, для тех у кого есть ключ)

## Стратегия использования

### MVP (Phases 1-2)
- Только Groq для всего
- Простая конфигурация
- Быстрый старт

### Post-MVP (Phase 3+)
- Groq для orchestration
- Ollama tools для:
  - Суммаризация больших документов
  - Анализ кода
  - Генерация embeddings
  - Другие compute-intensive задачи

### Production (далекое будущее)
- Возможность выбора провайдера
- Fallback механизмы
- Load balancing между провайдерами

## Требования к системе

### Только Groq (текущая конфигурация)
- **RAM:** 4GB минимум
- **Диск:** ~500MB для проекта
- **Сеть:** Стабильное подключение

### Groq + Ollama (будущее)
- **RAM:** 8GB минимум (16GB рекомендуется)
- **Диск:** +2-10GB для Ollama моделей
- **GPU:** Опционально, но ускоряет Ollama

## Мониторинг использования

### Groq Dashboard
- [console.groq.com](https://console.groq.com/) — usage statistics
- Rate limits видны в dashboard

### Ollama (локальное)
```bash
# Проверить установленные модели
ollama list

# Проверить использование ресурсов
ollama ps

# Удалить неиспользуемые модели
ollama rm <model-name>
```

---

**Следующий шаг:** Реализовать LLM Adapter в Phase 1 с поддержкой Groq
