# Live acceptance внешних метеорологических провайдеров

Дата актуализации: **2026-07-13**.

## Назначение

Mocked HTTP-contracts и unit-тесты проверяют детерминированную логику, но не могут подтвердить, что фактические Open-Meteo endpoints продолжают отдавать совместимую структуру, локальные даты и доступный ERA5-Land ряд. Для релевантных изменений CI запускает отдельный read-only job с реальными запросами.

Live acceptance не изменяет PostgreSQL, Redis или Telegram-состояние и не отправляет сообщения пользователям.

## Оперативный Open-Meteo contract

```bash
python -m src.ops.provider_smoke \
  --latitude 55.75 \
  --longitude 37.62 \
  --season-start YYYY-MM-DD
```

Проверяются обязательные суточные поля, IANA timezone, timezone-aware retrieval timestamp, уникальность и непрерывность локальных дат, соответствие coverage, корректное разделение completed/forecast и полный historical coverage от запрошенной даты сезона.

Текущий локальный день обязан находиться только в `forecast/current_forecast`. Completed rows на текущей или будущей дате и forecast rows в завершённом прошлом считаются ошибкой контракта.

## Однородный ERA5-Land contract

```bash
python -m src.ops.climate_smoke \
  --latitude 55.75 \
  --longitude 37.62 \
  --season-start YYYY-MM-DD \
  --crop wheat
```

Проверяются одна модель `era5_land` для текущего и reference-периода, точное покрытие 1991–2020, только reanalysis provenance, завершённый текущий период, отсутствие полностью пустого хвоста, минимум 20 reference-лет и обязательные temperature/precipitation/ET₀/GDD metrics.

## CI и evidence

Job `Live provider contracts (relevant PRs)` находится в основном workflow `CI`. Внешние запросы выполняются только когда diff затрагивает provider/science/smoke-контракты или production requirements.

Результаты сохраняются на 14 суток:

```text
operational-smoke.json
climate-smoke.json
```

Обычные изменения не зависят от внешней доступности API. Релевантный provider PR не принимается при несовместимом live contract.

## Ограничения

Live smoke одной контрольной точки подтверждает API-контракт, но не качество конкретного поля и не региональную точность реанализа. Для научной валидации остаются обязательными сравнение со станциями, оценка bias по регионам и сезонам, а для критических предупреждений — независимый резервный канал.
