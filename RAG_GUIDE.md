# 📚 Опциональная база знаний RAG

RAG не входит в core dependency profile. Он включается только после установки `requirements-rag.txt`, индексации документов и явного `RAG_ENABLED=true`.

## Ограничения безопасности

- ответ должен опираться на найденные документы;
- источник и страница показываются пользователю;
- отсутствие контекста не заменяется свободной агрономической рекомендацией;
- дозы препаратов, удобрений и защитные мероприятия нельзя выдавать без нормативного источника и конкретного контекста;
- погодные расчёты выполняются детерминированным application layer, а не LLM;
- при ошибке LLM пользователь получает найденные источники и сообщение о недоступности, а не выдуманный ответ.

## Установка профиля

Локально:

```bash
pip install -r requirements-rag.txt
```

Production:

```dotenv
INSTALL_RAG_PROFILE=1
RAG_ENABLED=true
```

После изменения выполните обычный update, чтобы новый virtualenv получил optional dependencies.

## Документы

Поддерживаются PDF с текстовым слоем, TXT и Markdown.

```text
data/literature/
```

Production path:

```text
/var/lib/crop-forecast-bot/data/literature/
```

Сканированные PDF сначала должны получить корректный текстовый слой. OCR не выполняется ботом автоматически.

## Индексация

```bash
python -m src.knowledge.indexer
python -m src.knowledge.indexer --reset
python -m src.knowledge.indexer --info
```

## LLM provider

Текущий adapter использует OpenAI-compatible API.

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=...
```

Допустимые значения:

- `groq` + `GROQ_API_KEY`;
- `together` + `TOGETHER_API_KEY`;
- `openai` + `OPENAI_API_KEY`;
- `ollama` для локального OpenAI-compatible endpoint.

Ключи хранятся только в runtime env, не в репозитории.

## Что ещё требуется до mature release

- document version/date/category metadata;
- проверка цитаты на соответствие реально retrieved chunk;
- prompt-injection tests;
- evaluation set русскоязычных агрономических вопросов;
- строгий policy guard для нормативных рекомендаций.
