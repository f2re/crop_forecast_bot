# Live GFS Ensemble provider evidence

Дата проверки: **2026-07-17**.

## Контекст

Проверка выполнена workflow `Ensemble provider smoke` из PR #37 для production-адаптера `OpenMeteoEnsembleProvider`.

- workflow run: `29571586547`;
- job: `Live GFS ensemble contract`;
- head SHA: `272f0e5f1e9ad1276a58809be210ae6f03b4d472`;
- artifact: `ensemble-provider-smoke-29571586547`;
- artifact id: `8403301545`;
- artifact digest: `sha256:28be262b12194de27c96c72cbed72acfd8ba716d3d1324b5ea9ed5bf19875bf9`;
- срок хранения GitHub artifact: до `2026-07-31T09:54:20Z`.

## Фактический результат

```json
{
  "ok": true,
  "latitude": 55.75,
  "longitude": 37.5,
  "elevation_m": 152.0,
  "timezone": "Europe/Moscow",
  "source": "NOAA GFS Ensemble via Open-Meteo Ensemble API",
  "model": "gfs_seamless",
  "retrieved_at": "2026-07-17T09:54:19.369424+00:00",
  "cache_ttl_seconds": 10800,
  "member_count": 31,
  "forecast_days": 16,
  "rows": 496,
  "local_date_start": "2026-07-17",
  "local_date_end": "2026-08-01",
  "complete_days": 16,
  "incomplete_days": 0,
  "emitted_risk_events": 3
}
```

## Проверенные инварианты

- source, model, timezone и aware retrieval timestamp присутствуют;
- 31 уникальный член ансамбля;
- 16 последовательных локальных суток;
- 496 уникальных строк `дата × член`;
- Tmin, Tmax, осадки, порывы и CAPE имеют минимум 20 валидных членов для каждого дня;
- нет отрицательных осадков, порывов или CAPE;
- Tmin не превышает Tmax;
- весь горизонт принят `calc_ensemble_risks` без неполных суток;
- JSON evidence успешно загружен workflow artifact.

## Что эта проверка не доказывает

- точность прогноза в поле;
- региональную калибровку;
- вероятность ущерба культуре;
- вероятность града;
- устойчивость внешнего API при длительной эксплуатации.

Для этих выводов нужны архив прогнозов и наблюдений, станционное сравнение, reliability/Brier/ROC/PR и полевая приёмка.
