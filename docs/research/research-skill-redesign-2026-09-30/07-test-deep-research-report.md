# Report 2

## Summary

Тезис «на Reddit нельзя доверять вообще ничему» данными не подтверждается, но и обратное не доказано: единственное рецензируемое измерение даёт низкие единицы процентов машинного текста с пиками до ~9% в отдельных сабреддитах и месяцах, причём это заниженная оценка по длинным текстам до декабря 2024, а dev-сабреддиты в выборку почти не попали. По астротурфингу именно в programming-сабреддитах ни одного подтверждённого измерения не нашлось — это пробел в данных, не свидетельство чистоты. Польза форумов доказана только для Stack Overflow (в среднем 34.4% сниппетов знаний, извлечённых из SO, отсутствуют в официальной документации); на Reddit это переносится лишь по аналогии. Вывод: канал можно оставить только как источник гипотез с обязательным независимым подтверждением; апвоты фильтром не служат. Режим «только сниппеты» от отравления не защищает: атака 13 словами показана именно на SERP-сниппетах, а встроенные deep-research агенты сами опираются на одни и те же Reddit-страницы. Вопрос о сравнении со встроенным deep-research этим прогоном не исследовался.

## Findings

### F1. Измеренная доля машинно-сгенерированного текста (MGT) на Reddit мала в среднем, но неравномерна: при консервативной настройке детектора помесячные пики доходят до ~9% в отдельных сабреддитах. Это заниженная оценка, а не истинная распространённость, и она не покрывает 2025-2026 и dev-сабреддиты.

- confidence: medium; vote: 3-0 (claims 0, 1)
- sources: https://arxiv.org/html/2510.07226v1
- evidence: La Cava, Aiello, Tagarelli (arXiv 2510.07226, позже опубликована в рецензируемом журнале Online Social Networks and Media). Метод: Fast-DetectGPT, порог 0.99, только тексты от 250 токенов; 9.03M комментариев и 2.13M постов из 51 крупного сабреддита, январь 2022 - декабрь 2024. Пики по комментариям: r/teenagers 8.46%, r/malefashionadvice 7.69%, r/askscience 6.33%, r/politics 1.28%. Авторы прямо пишут, что метод не даёт точной распространённости и что снижение порога с 0.99 до 0.95 уже удваивает оценку (одно предложение, без таблицы). Короткие комментарии исключены. Из tech-сабреддитов в выборке только r/technology, r/learnprogramming, r/techsupport; r/programming и tool-specific сабреддитов нет. Строгой нижней границей это тоже не является: сигнал в r/teenagers есть и до появления ChatGPT, то есть часть срабатываний ложная. Измеряется MGT, а не боты и не астротурфинг: написанный человеком шиллинг детектору не виден. Средняя уверенность, потому что исследование одно (внутри него цитируется Sun et al. 2024 с ~2.5% того же порядка, но я его не проверял).

### F2. MGT сконцентрирован в небольшой группе аккаунтов и смещён в сторону сабреддитов обмена техническими знаниями и social support; апвоты его не отсеивают.

- confidence: medium; vote: 3-0 (claims 2, 3)
- sources: https://arxiv.org/html/2510.07226v1
- evidence: Тот же источник. На пике около 2% активных пользователей дают весь обнаруженный MGT (максимум 3%, после пика меньше 2%); у этих пользователей 10-40% постов машинные, в установившемся режиме около 20%. Information Seeking даёт 29.83% всего обнаруженного MGT при 1.6M из 9.0M комментариев, то есть перепредставлен; Social Support 26.73%, но это отчасти эффект объёма (4.5M комментариев). По вовлечённости: из 102 сравнений «сабреддит-месяц» в 26 разница значима, и в 25 из них MGT получал более высокий net score, чем человеческий текст (r/technology: 3 месяца, средний Cliff's delta 0.27); в остальных 76 значимой разницы не найдено. Оговорки: матчинг слабый (только сабреддит + месяц), без поправки на множественные сравнения, 76 случаев — это не доказанная эквивалентность, эффекты малы (delta 0.2-0.3), ни один значимый случай не относится к programming-сабреддиту. «Апвоты не фильтруют» — вывод из этих данных, не формулировка авторов.

### F3. Исследование Siege Media / Pangram с высокими долями AI-постов по сабреддитам (r/TechSEO 75%, r/ClaudeAI 40% и т.д.) нельзя использовать как оценку распространённости: выборка неслучайная, ячейки по 4-10 постов, источник маркетинговый.

- confidence: low; vote: 3-0 (claims 4, 5); связанное утверждение отвергнуто 0-3
- sources: https://www.siegemedia.com/research/ai-use-in-reddit-citations
- evidence: 802 поста из 384 сабреддитов, сбор 2 февраля - 31 марта 2026. Выборка — посты из топовых Reddit-URL, цитируемых в ответах AI-поиска, а не случайный срез Reddit. Категория 'Highly Likely AI' включает также 'Likely' и 'Possibly AI-generated'. На странице нет ни false-positive rate, ни доверительных интервалов, ни сырых данных; боты и астротурфинг не упоминаются. По сабреддитам: r/TechSEO 75% (n=4), r/recruiting 50% (n=10), r/GrowthHacking 50% (n=4), r/ClaudeAI 40% (n=5), r/CRM 40% (n=5), r/legaltech 38% (n=8), r/localseo 33% (n=6); порог включения — от 4 постов. Ни одного core programming сабреддита нет. Siege — GEO-агентство, Pangram — вендор детектора, страница заканчивается продажей. Утверждение «0.215 в tech против 0.001 в non-tech» верификацию не прошло (0-3) и в отчёт не входит. Полезный остаток только один: посты, которые цитирует AI-поиск, заметно чаще помечаются как AI в маркетинговых/SEO/SaaS-нишах — качественный сигнал, не число.

### F4. Transparency report Reddit за H1 2025 не измеряет долю бот- или AI-контента и не может ни подтвердить, ни опровергнуть оценки этой доли; его цифры — это объём модерации.

- confidence: high; vote: 3-0 (claims 6, 7, 8)
- sources: https://redditinc.com/policies/transparency-report-january-to-june-2025-reddit
- evidence: Из ~6 млрд единиц контента за январь-июнь 2025 удалено ~2.66% (1.41% модераторами, 1.25% админами), всего 158,025,279 единиц, включая личные сообщения и чат. Спам — 57.5% удалений админов; прочая content manipulation (манипуляция голосами и искусственное продвижение) — 0.6%. Производная оценка: удалённый админами спам составляет ~0.7% всего созданного контента (в отчёте этой цифры нет; удаления модераторов по причинам не разбиты, так что всего обнаруженного спама больше). Категории для AI-контента или бот-аккаунтов в отчёте нет: проверены и текст, и графики категорий; слово 'bots' встречается один раз и относится к модераторским ботам. Необнаруженный неаутентичный контент в эти цифры по построению не попадает, поэтому цитировать их как «на Reddit всего 0.7% спама/ботов» нельзя. Уверенность высокая, потому что это утверждение о содержании самого документа; сам отчёт — самоотчётность компании, и за H2 2025, вероятно, уже есть более свежий.

### F5. Документированных измерений астротурфинга именно в technology/programming сабреддитах среди подтверждённых утверждений нет. Подвопрос (2) остался без ответа: это отсутствие данных, а не свидетельство отсутствия манипуляций.

- confidence: low; vote: нет прямых утверждений; косвенно claims 5, 7
- sources: https://redditinc.com/policies/transparency-report-january-to-june-2025-reddit, https://www.siegemedia.com/research/ai-use-in-reddit-citations, https://arxiv.org/html/2510.07226v1
- evidence: Ближайшие косвенные данные: (a) 0.6% удалений админов по категории content manipulation — только пойманное, и аккаунты-астротурферы, пойманные антиспамом, учитываются как спам; (b) повышенные AI-флаги в маркетинговых/SEO/SaaS-сабреддитах по слабому исследованию Siege; (c) детектор MGT человеческий шиллинг не видит. В одной из проверок упомянут эксперимент Цюрихского университета в r/changemyview, который Reddit не обнаружил, но как отдельное утверждение он не верифицировался. Ни один источник не измерял r/programming, r/ExperiencedDevs, r/devops и подобные.

### F6. Форумы разработчиков действительно содержат знания, которых нет в официальной документации, но доказано это только для Stack Overflow; на Reddit это переносится по аналогии. Сам форумный контент при этом — источник ошибок.

- confidence: high; vote: 3-0 (claims 9, 10, 11, 12, 13, 14)
- sources: https://arxiv.org/abs/2601.08036, https://dl.acm.org/doi/abs/10.1145/2884781.2884800, http://chrisparnin.me/pdf/crowddoc.pdf
- evidence: AutoDoc (ICSE 2026): на 48 API (Java, Android, Kotlin, TensorFlow) в среднем 34.4% сниппетов знаний, сгенерированных из постов SO, не покрыты официальной документацией; для популярных API доля нового выше (~42% против ~29%). Это свойство выхода пайплайна retrieval + GPT-4o, а не сырого SO. Из 38 ошибочных сниппетов 5 (13.2%) восходят к неверной информации в самих постах SO, 14 (36.8%) — неверная интерпретация LLM, 19 (50%) — галлюцинации без опоры на SO; при ~96.2% точности это около 0.5% всех сниппетов. Фильтр score >= 5 применялся только к обучающей выборке ретривера, не к корпусу поиска, так что это не доказательство провала фильтра по оценкам. Treude & Robillard (ICSE 2016): 8 разработчиков, SISE дал 47.5% оценок «добавляет полезное, чего нет в документации» против 22.5-32.5% у конкурентов; согласие оценщиков низкое (43% пар), сверка с документацией не контролировалась, только Java. Parnin et al. (2012, техотчёт): на SO есть хотя бы один тред для 87% классов Android API и 77% Java (GWT — 54%); это широта покрытия, а сравнение с документацией там — один иллюстративный пример (invokeLater: один пример кода против 286 вопросов). Авторы отдельно оговаривают, что результаты могут не переноситься на Reddit. Уверенность высокая только для SO; для Reddit прямых данных ноль.

### F7. После запуска ChatGPT оставшийся на Stack Overflow контент сместился к более длинным и сложным вопросам; авторы трактуют это как сохранение ценности краудового Q&A для задач, с которыми LLM справляются хуже.

- confidence: medium; vote: 3-0 (claims 20, 21)
- sources: https://arxiv.org/html/2509.05879v1
- evidence: Helic & Santos (Journal of Systems and Software, 2026). Difference-in-differences: длина вопроса +6-8% стандартного отклонения, длина ответа до ~5% SD, длина примеров кода +21% SD для python, сложность +11% SD для java (это SD вероятности класса 'medium'). Сложность — прокси: XGBoost поверх эмбеддингов CodeT5, обученный на метках LeetCode easy/medium/hard, без валидации на вопросах SO и без человеческой разметки. Сдвиг идёт от easy к medium; для hard коэффициенты незначимы. Окно наблюдения заканчивается примерно в апреле-мае 2023, так что это не измерение 2025-2026. Качество ответов и отсутствие знаний в документации не измерялись; вывод «простое уходит в ChatGPT, сложное — в сообщество» — интерпретация авторов.

### F8. У GitHub собственные измеренные риски манипуляции и AI-slop, но они касаются звёзд и PR, а не текста issues/discussions. По Hacker News ни одного подтверждённого утверждения нет, поэтому сравнение четырёх площадок по одним и тем же рискам не состоялось.

- confidence: medium; vote: 3-0 (claims 15, 16, 17, 18)
- sources: https://arxiv.org/abs/2412.13459, https://arxiv.org/abs/2607.04003
- evidence: StarScout (arXiv 2412.13459 v2, ICSE'26), все события GitHub с июля 2019 по декабрь 2024: ~6.0M подозрительных звёзд в 26,254 репозиториях до постобработки; после неё 18,617 репозиториев с кампаниями, ~301k аккаунтов, 3.81M звёзд. Фальшивые звёзды — не более ~1% всех звёзд в месяц, но в июле 2024 кампании были у 16.66% «популярных» репозиториев (3,499; «популярный» = от 50 звёзд за этот месяц). Детекция эвристическая, всё это «suspected»; большинство помеченных репозиториев — короткоживущие фишинговые/malware, позже удалённые. Вывод для агента: число звёзд как сигнал качества ненадёжно. 'AI Slop is DDoSing Open Source' (arXiv 2607.04003, препринт): 294 репозитория, более 2M PR и issues; в 2025 объём PR вырос на 6.80%, merge rate у разовых контрибьюторов на 18.18% ниже контрфактического (BSTS), в целом на 1.06%. AI-контент напрямую не измерялся: 2025 год взят как окно вмешательства, другие изменения экосистемы не исключены, так что 18.18% — не доля AI-контента. Гипотезы о росте числа issues не подтвердились, а плацебо-тесты по метрикам issues дали значимые эффекты. Данных о надёжности текста GitHub issues/discussions и о ботах/астротурфинге на HN нет.

### F9. Deep-research агенты по популярным темам систематически опираются на одни и те же UGC-страницы, прежде всего Reddit, и это делает одну страницу выгодной мишенью для отравления. В симуляции 13 добавленных слов хватало, чтобы текст атакующего попадал в выдачу в 57-76% запусков и цитировался в 38-51% отчётов.

- confidence: medium; vote: 3-0 (claim 22), 2-1 (claim 23)
- sources: https://arxiv.org/abs/2605.24245
- evidence: Zhang, Triedman, Shmatikov (Cornell Tech, препринт, май 2026, v2 сентябрь 2026). 11 тематических кластеров, 176 запросов; отдельные UGC-страницы извлекаются до 48% запросов кластера; Reddit — 54-71% UGC-URL у STORM/Co-STORM/OmniThink. UGC — меньшинство источников: 17-23% извлечённых URL у open-source агентов и 12.1% цитат Gemini Deep Research (623 из 5,157); при этом у Gemini DR 102 повторяющихся UGC-URL, один процитирован в 19 из 22 запросов кластера. Ограничения: отравление симулировалось на уровне retrieval, живой контент не менялся; end-to-end атака проверена только на трёх open-source системах, на OpenAI и Gemini Deep Research — нет; выживаемость яда при реальной модерации не оценивалась; темы потребительские (финансы, товары, рестораны), dev-инструментов среди кластеров нет. Важно для решения «тогда сниппеты»: результат с 13 словами получен именно в режиме SERP-сниппетов, а полный текст треда атаку ослабляет, но не нейтрализует. Отсюда мой вывод (не измерение): чтение только сниппетов не защищает от отравления и, возможно, усиливает его эффект; замена своего пайплайна встроенным deep-research зависимость от Reddit сама по себе не убирает.

### F10. Есть прецедент методически корректного использования Reddit в исследовании: как один из трёх независимых источников для формулирования гипотез, с последующей проверкой на данных репозиториев, а не как самостоятельное доказательство.

- confidence: low; vote: 3-0 (claim 19)
- sources: https://arxiv.org/abs/2607.04003
- evidence: Afroz et al. (arXiv 2607.04003): этап 1 — триангуляция по трём источникам серой литературы (r/opensource: 34 треда-кандидата, 24 отобрано, 334 комментария; рассылка OSS-менторов; блоги практиков); все шесть тем подтверждены сегментами из всех трёх источников. Этап 2 — проверка гипотез на трассах 294 репозиториев, с неоднозначным результатом: гипотезы по PR подтвердились, по issues — нет. Авторы защищались от смещения «громкого меньшинства», а не от ботов или AI-контента на Reddit: этот риск в статье не рассматривается. Один препринт — это образец практики, а не доказательство её достаточности. Применимо к агенту как шаблон: Reddit порождает гипотезу, подтверждает её независимый источник или первичные данные.


## Caveats

1. Главное число по Reddit опирается на одно исследование с данными до декабря 2024 и только по текстам от 250 токенов. Для 2025-2026 и для dev-сабреддитов прямых измерений нет; реальная доля AI-текста, скорее всего, выше, но насколько — неизвестно.
2. MGT, боты и астротурфинг — три разные вещи. Измерен только MGT; человеческий шиллинг и координированное продвижение не измерены нигде.
3. Подвопрос (2) про астротурфинг в tech-сабреддитах и часть подвопроса (4) про Hacker News остались без подтверждённых данных. По GitHub данные есть только о звёздах и PR, не о тексте issues/discussions.
4. Польза форумов сверх документации доказана только для Stack Overflow; два из трёх источников — 2012 и 2016 годов, до LLM. Перенос на Reddit — аналогия.
5. Источники неравноценны: Siege/Pangram — маркетинг с ячейками по 4-10 постов; отчёт Reddit — самоотчётность; работы про AI slop на GitHub и про отравление deep-research агентов — нерецензированные препринты. По утверждению про 13 слов голоса разделились 2-1, и сама атака симулирована.
6. Проверка на опровержения была неполной: у нескольких верификаторов поиск упирался в rate limit, и часть выводов опирается только на первичный источник.
7. Вывод про сниппеты — мой вывод из условий эксперимента с отравлением, а не измеренный результат для вашего пайплайна.
8. Вопрос «подойдёт ли встроенный deep-research, не переусложняем ли» этим исследованием не закрыт: сравнительный тест не проводился. Единственное относящееся к делу наблюдение — встроенные агенты тоже цитируют повторяющиеся Reddit-страницы.
9. Срок годности: доля AI-контента быстро меняется, цифры 2022-2024 нужно считать историческими; за H2 2025, вероятно, уже есть более свежий transparency report Reddit.

## Open questions

- Какова доля AI-текста и координированного продвижения именно в dev-сабреддитах (r/programming, r/ExperiencedDevs, r/devops, tool-specific) в 2025-2026? Ни один подтверждённый источник их не измерял.
- Даёт ли Reddit в нашем пайплайне утверждения, которые проходят верификацию и не находятся в других каналах? Это проверяется на собственных прогонах: доля выживших Reddit-утверждений против HN / SO / GitHub.
- Сравнительный тест со встроенным deep-research на одних и тех же вопросах: доля проверяемых утверждений, доля UGC в цитатах, стоимость и время. Без него вопрос «не переусложняем ли» остаётся открытым.
- Насколько Hacker News и текст GitHub issues/discussions подвержены тем же рискам? Измерений не найдено, поэтому замена Reddit на них пока не обоснована данными.

## Refuted

- {"claim": "AI-likelihood is concentrated in professional/tech communities: tech, marketing, SEO and SaaS subreddits averaged an AI-likelihood score of 0.215 versus 0.001 in non-tech communities, where 100% of posts were classed as unlikely to be AI-generated. (The companion figure '15.7% of tech-focused subreddits' is ambiguously worded in the source - it is unclear whether it is the share of tech posts flagged as AI or the share classed as unlikely AI.)", "vote": "0-3", "source": "https://www.siegemedia.com/research/ai-use-in-reddit-citations"}

## Unverified



## Sources

- {"url": "https://arxiv.org/html/2510.07226v1", "quality": "primary", "angle": "Measured prevalence: bots and AI-generated content on Reddit", "claimCount": 5}
- {"url": "https://originality.ai/blog/ai-reddit-posts-study", "quality": "blog", "angle": "Measured prevalence: bots and AI-generated content on Reddit", "claimCount": 5}
- {"url": "https://www.siegemedia.com/research/ai-use-in-reddit-citations", "quality": "primary", "angle": "Measured prevalence: bots and AI-generated content on Reddit", "claimCount": 5}
- {"url": "https://redditinc.com/policies/transparency-report-january-to-june-2025-reddit", "quality": "primary", "angle": "Measured prevalence: bots and AI-generated content on Reddit", "claimCount": 5}
- {"url": "https://originality.ai/blog/ai-in-seo-marketing-subreddits", "quality": "blog", "angle": "Measured prevalence: bots and AI-generated content on Reddit", "claimCount": 5}
- {"url": "https://www.reddit.com/r/dataisbeautiful/comments/1ux46i9/oc_how_much_of_reddit_is_aiwritten_i_scored_20000/", "quality": "forum", "angle": "Measured prevalence: bots and AI-generated content on Reddit", "claimCount": 5}
- {"url": "https://www.404media.co/ai-is-poisoning-reddit-to-promote-products-and-game-google-with-parasite-seo/", "quality": "secondary", "angle": "Documented astroturfing and manipulation in tech subreddits", "claimCount": 5}
- {"url": "https://tech.slashdot.org/story/26/06/04/1828244/companies-are-using-reddit-to-manipulate-chatgpt-and-google-ai-search", "quality": "secondary", "angle": "Documented astroturfing and manipulation in tech subreddits", "claimCount": 5}
- {"url": "https://www.washingtonpost.com/technology/2025/04/30/reddit-ai-bot-university-zurich/", "quality": "secondary", "angle": "Documented astroturfing and manipulation in tech subreddits", "claimCount": 2}
- {"url": "https://larslofgren.com/codesmith-reddit-reputation-attack/", "quality": "blog", "angle": "Documented astroturfing and manipulation in tech subreddits", "claimCount": 5}
- {"url": "https://arxiv.org/abs/2601.08036", "quality": "primary", "angle": "Academic evidence: forums carry knowledge absent from official docs", "claimCount": 5}
- {"url": "https://dl.acm.org/doi/abs/10.1145/2884781.2884800", "quality": "primary", "angle": "Academic evidence: forums carry knowledge absent from official docs", "claimCount": 4}
- {"url": "http://chrisparnin.me/pdf/crowddoc.pdf", "quality": "primary", "angle": "Academic evidence: forums carry knowledge absent from official docs", "claimCount": 5}
- {"url": "https://2019.icse-conferences.org/details/icse-2019-Technical-Papers/49/Software-Documentation-Issues-Unveiled", "quality": "primary", "angle": "Academic evidence: forums carry knowledge absent from official docs", "claimCount": 4}
- {"url": "https://arxiv.org/abs/2412.13459", "quality": "primary", "angle": "Cross-platform comparison: Hacker News, Stack Overflow, GitHub", "claimCount": 5}
- {"url": "https://arxiv.org/abs/2607.04003", "quality": "primary", "angle": "Cross-platform comparison: Hacker News, Stack Overflow, GitHub", "claimCount": 5}
- {"url": "https://academic.oup.com/pnasnexus/article/3/9/pgae400/7754871", "quality": "primary", "angle": "Cross-platform comparison: Hacker News, Stack Overflow, GitHub", "claimCount": 5}
- {"url": "https://arxiv.org/html/2509.05879v1", "quality": "primary", "angle": "Cross-platform comparison: Hacker News, Stack Overflow, GitHub", "claimCount": 5}
- {"url": "https://news.ycombinator.com/item?id=47340079", "quality": "forum", "angle": "Cross-platform comparison: Hacker News, Stack Overflow, GitHub", "claimCount": 5}
- {"url": "https://meta.stackexchange.com/questions/408728/the-number-of-questions-has-decreased-30-fold-where-did-users-go-and-what-can-b", "quality": "forum", "angle": "Cross-platform comparison: Hacker News, Stack Overflow, GitHub", "claimCount": 5}
- {"url": "https://arxiv.org/abs/2605.24245", "quality": "primary", "angle": "Skeptical/practitioner: should an AI agent cite Reddit, and with what safeguards", "claimCount": 5}
- {"url": "https://www.404media.co/it-is-trivially-easy-to-use-reddit-to-manipulate-ai-search-research-suggests/", "quality": "secondary", "angle": "Skeptical/practitioner: should an AI agent cite Reddit, and with what safeguards", "claimCount": 5}
- {"url": "https://thenextweb.com/news/reddit-ai-marketing-slop-geo-crackdown", "quality": "secondary", "angle": "Skeptical/practitioner: should an AI agent cite Reddit, and with what safeguards", "claimCount": 5}