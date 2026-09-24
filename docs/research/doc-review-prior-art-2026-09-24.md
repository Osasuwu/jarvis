---
title: Prior art для LLM-ревьюера фактических утверждений в документации — готовые решения, методика оценки, утечка будущего в снапшотах
topic: doc-review-prior-art
tags: area:docs-review, research
date: 2026-09-24
status: draft
depth: prior-art-scan
sources_count: 19
source_provenance: поиск prior art перед calibration 2 review-doc (jarvis-oss #143, #138, #150), 2026-09-24; дополняет agent-reviews-agent-2026-09-19.md
confidence: 65
---

> Лежит в `jarvis/docs/research/`, а не в `jarvis-oss/docs/research/`, по той же причине, что и
> [agent-reviews-agent-2026-09-19.md](agent-reviews-agent-2026-09-19.md): structure-gate
> jarvis-oss требует от каждого `docs/**/*.md` фронтматтер практик-дока.

Метки: **[read]** — источник открыт; **[snippet]** — только текст поисковой выдачи, не проверен.

## Summary

Готового решения под нашу задачу нет. Все найденные инструменты делают что-то соседнее:
- сверяют комментарии или API-доки с кодом (DocPrism, CASCADE);
- ловят устаревание документа после диффа (Drift, Swimm, doc-drift);
- проверяют вывод LLM против источников (Claimify, sourcecheck).

Прозаические утверждения уровня репо — «файл существует», «tried», «sourced», «список полон» —
против репо и его истории не проверяет никто. Ревьюер остаётся нашим.

Методика калибровки 1 совпадает с полевой. SWR-Bench (FSE 2026) построен так же, как наш корпус:
реальные сбежавшие дефекты, снапшот «перед первым ручным ревью», LLM-матчер находок. Он же
показывает огромный разброс между одинаковыми прогонами.

Кандидат 1 (#146) уже совпадает с литературой: извлечение утверждений, дословная выдержка,
рассуждение перед вердиктом, куски. Реально новое одно: **объединение находок k прогонов**, у
которого самый большой найденный эффект (+118,8 % recall). Фикс утечки через снапшоты
соответствует полевому правилу «нет будущих файлов», но три канала, которые поле закрывает, у
нас открыты: git refs, сеть и метаданные.

## Key Findings

### 1. Готовые инструменты сверки документации с кодом

- **DocPrism** ([arXiv 2511.00215](https://arxiv.org/abs/2511.00215)) [read, abstract].
  - LLM ищет несоответствия doc/code на уровне функции.
  - Схема «локальная классификация, потом внешний фильтр» снизила долю флагов с 98 % до 14 %,
    F1 вырос с 0,22 до 0,77.
  - Проверяет комментарии к коду, а не утверждения уровня репо.
  - Вердикт: **идея**.
- **CASCADE** ([arXiv 2604.19400](https://arxiv.org/abs/2604.19400), FSE 2026) [read, abstract].
  - Превращает документ в тесты. Несоответствие засчитывается, только когда согласны два
    независимых сигнала.
  - Наши утверждения не исполнимы.
  - Вердикт: **не применимо**, кроме правила «два сигнала должны совпасть».
- **Fiberplane Drift** ([repo](https://github.com/fiberplane/drift)) [read].
  - Детерминированный, без LLM: привязывает Markdown к файлам и символам и сравнивает
    tree-sitter-отпечатки между коммитами. Точность не публикует.
  - Вердикт: **идея** — утверждения о путях («`.gitleaks.toml` существует») проверять
    детерминированно, не суждением LLM.
- **sourcecheck** ([repo](https://github.com/qwertymuzaffar/sourcecheck)) [read].
  - Ищет цитаты в источнике: точное, нормализованное и нечёткое совпадение.
  - Вердикт: **идея** — сверка цитаты со строкой не требует LLM.
- **Claimify** ([MSR blog](https://www.microsoft.com/en-us/research/blog/claimify-extracting-high-quality-claims-from-language-model-outputs/))
  и **VeriScore** ([arXiv 2406.19276](https://arxiv.org/pdf/2406.19276)) [snippet].
  - Стандартный конвейер: разложить на утверждения, найти источник, проверить.
  - Вердикт: **идея**, уже заложенная в кандидат 1.
- **Anthropic code-review plugin**
  ([repo](https://github.com/anthropics/claude-code/tree/main/plugins/code-review)) [snippet].
  - Пять параллельных специализированных ревьюеров и фильтр по уверенности ≥80. Фильтр
    настроен на precision, не на recall.
  - Вердикт: **идея** — взять специализацию, фильтр не брать.
- **Swimm**, **doc-drift**, **driftcheck** [snippet / read].
  - Работают только в своём формате или от диффа PR, точность не публикуют.
  - Вердикт: **не применимо**.

### 2. Методика оценки ревьюеров

- **SWR-Bench** ([arXiv 2509.01494](https://arxiv.org/html/2509.01494v2), FSE 2026) [read].
  - Устройство: 1000 реальных PR (500 с изменениями, 500 чистых), дефекты из истории PR плюс
    SZZ, заморозка перед первым ручным ревью. LLM-матчер согласен с людьми примерно в 90 %
    случаев.
  - Recall падает с 38 % (одно изменение) ниже 20 % (пять и больше).
  - Из пяти прогонов одной модели общих находок только 27.
  - Вердикт: **идея**; подтверждает наш метод и шумность одиночного прогона.
- **τ-bench** ([arXiv 2406.12045](https://arxiv.org/abs/2406.12045)) [snippet].
  - pass@k — «успех хоть в одном из k», pass^k — «успех во всех k». У gpt-4o: больше 60 % при
    pass^1, меньше 25 % при pass^8.
  - Вердикт: **идея** — печатать catch@3 и catch^3 рядом с per-run.
- **ContextCRBench** ([arXiv 2511.07017](https://arxiv.org/abs/2511.07017)),
  **Martian Code Review Bench**, **Greptile benchmark** [snippet].
  - Код-диффы, огромный масштаб или вендорские прогоны без штрафа за ложные срабатывания.
  - Вердикт: **не применимо**.

### 3. Утечка будущего в снапшотах репо

- **SWE-bench #465** ([link](https://github.com/SWE-bench/SWE-bench/issues/465)) [read],
  2025-09-03.
  - Агенты, среди них Claude Sonnet, находили будущие фиксы через `git log --all`, `--grep`,
    reflog, remote-ветки и теги.
  - Предложенный фикс: удалить remotes и ветки, вычистить reflog. Что в итоге выкатили, со
    страницы не видно.
- **SWE-bench Pro OSS #93** ([link](https://github.com/scaleapi/SWE-bench_Pro-os/issues/93))
  [read], 2026-04-29.
  - Эксплойт работал на 100 % публичных образов.
  - Фикс: срезать коммиты после целевого, `reflog expire`, `gc --prune`.
- **SWE-Bench Pro Verified** ([arXiv 2609.08149](https://arxiv.org/html/2609.08149)) [read].
  - Четыре канала утечки: локальные файлы; git-история (будущие коммиты, ветки, теги,
    remotes, reflog); сеть (raw, API и object-эндпоинты GitHub); метаданные задачи (целевой
    SHA, ID).
  - Фикс: свежий репо из одного коммита, блокировка сети, хешированные ID.
  - Эффект: у GLM-5.2 результат упал с 78,80 % до 57,32 %, у DeepSeek-V4-Pro сдвинулся лишь на
    0,87 п.п.
- **SWE-rebench** ([arXiv 2505.20411](https://arxiv.org/abs/2505.20411)) [snippet].
  - Другой канал — загрязнение обучающих данных; берут только задачи новее cutoff модели.
  - Для нас не проверено.

### 4. Что измеримо поднимало recall

- **Объединение k прогонов** (SWR-Bench) [read].
  - n прогонов, отчёты сливает LLM. У Gemini-2.5-Flash при n = 10: recall +118,8 % (до
    30,44 %), F1 +43,7 %. При n = 5 F1 вырос с 15,25 % до 20,48 %.
  - Пять слитых прогонов Flash дешевле и лучше по F1, чем один прогон Pro.
  - Самый большой найденный эффект.
- **Специализированные роли** (Kuaishou, [arXiv 2505.17928](https://arxiv.org/abs/2505.17928))
  [read, abstract].
  - Около 2× к обычной LLM; в абстракте только относительные числа.
- **Предостережение** ([arXiv 2508.12358](https://arxiv.org/abs/2508.12358)) [read, abstract].
  - Просьба объяснить и предложить фикс *увеличила* долю ошибочных суждений. Длиннее промпт —
    не значит лучше проверка.

## Что меняется в дизайне

Сверено с планом calibration 2 в `jarvis-oss/.agents/skills/review-doc/CALIBRATION.md` на
2026-09-24.

| # | Изменение | Статус |
|---|---|---|
| 1 | Скоринг печатает catch@3 (объединение: поймано хоть в одном прогоне) и catch^3 (во всех) рядом с per-run | Новое. Правка Scoring замороженного плана — через `/grill` |
| 2 | Проход, сливающий находки k прогонов, как кандидат | Новое. Стоимость растёт линейно с k, мерить против 5-часового лимита |
| 3 | Извлечение утверждений, затем проверка каждого по типу | Уже кандидат 1 (#146), литература подтверждает |
| 4 | Детерминированные проверки для путей и цитат | Совпадает с выводом 6 из research 09-19 (`check_quotes`, structure-gate) |
| 5 | Dispatch-прогоны: оставить предков HEAD, снести remotes, ветки, теги и reflog | Исправляет AC #150 («только head commit» отрезает историю, по которой ловится `tried`) |
| 6 | Находка, опирающаяся на живое состояние GitHub, помечается как загрязнённая | Правило скоринга: сеть закрыть нельзя, она нужна для проверки цитат |

## Trade-offs & Risks

- **Эффект объединения k прогонов измерен на код-ревью** и Gemini Flash, не на прозе и не на
  Opus. Перенос не проверен.
- **catch@3 — не recall одного ревью.** Если в проде идёт один прогон, catch@3 описывает
  пайплайн, которого нет. Печатать его только рядом с per-run и с явной подписью.
- **Много [snippet]-источников в §1–2.** Выводы, опирающиеся только на них (Claimify, Martian,
  Greptile, плагин Anthropic), слабее остальных.

## Sources

1. DocPrism (arXiv 2511.00215) — https://arxiv.org/abs/2511.00215
2. CASCADE (arXiv 2604.19400) — https://arxiv.org/abs/2604.19400
3. Fiberplane Drift — https://github.com/fiberplane/drift
4. Swimm Auto-sync — https://swimm.io/blog/how-does-swimm-s-auto-sync-feature-work
5. doc-drift — https://github.com/jbrockSTL/doc-drift
6. driftcheck — https://github.com/deichrenner/driftcheck
7. sourcecheck — https://github.com/qwertymuzaffar/sourcecheck
8. Claimify — https://www.microsoft.com/en-us/research/blog/claimify-extracting-high-quality-claims-from-language-model-outputs/
9. VeriScore (arXiv 2406.19276) — https://arxiv.org/pdf/2406.19276
10. Anthropic code-review plugin — https://github.com/anthropics/claude-code/tree/main/plugins/code-review
11. SWR-Bench (arXiv 2509.01494) — https://arxiv.org/html/2509.01494v2
12. ContextCRBench (arXiv 2511.07017) — https://arxiv.org/abs/2511.07017
13. Martian Code Review Bench — https://codereview.withmartian.com/
14. Greptile benchmark — https://www.greptile.com/benchmarks
15. τ-bench (arXiv 2406.12045) — https://arxiv.org/abs/2406.12045
16. SWE-bench #465 — https://github.com/SWE-bench/SWE-bench/issues/465
17. SWE-bench Pro OSS #93 — https://github.com/scaleapi/SWE-bench_Pro-os/issues/93
18. SWE-Bench Pro Verified (arXiv 2609.08149) — https://arxiv.org/html/2609.08149
19. SWE-rebench (arXiv 2505.20411) — https://arxiv.org/abs/2505.20411

Также открыты: Kuaishou defect-focused ACR (arXiv 2505.17928) и Uncovering Systematic Failures
(arXiv 2508.12358) — только абстракты.

## Confidence: 65/100

Три главных вывода опираются на открытые источники:
- готового решения нет;
- метод совпадает с SWR-Bench;
- утечка через git refs — известный класс с известным фиксом.

Неуверенность в двух местах:
- перенос эффекта объединения прогонов с код-ревью на прозу;
- доля [snippet]-источников в обзоре инструментов.
