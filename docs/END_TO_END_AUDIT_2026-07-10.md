# Сквозной аудит runtime и расчётов — 2026-07-10

Проверен путь Telegram/FSM → PostgreSQL/Alembic → Open-Meteo → расчёты →
отчёт/RAG → scheduler/Redis → Bash/systemd.

## Исправленные P0/P1-дефекты

1. Прошлое и прогноз теперь разделяются по `data_kind`, а не сравнением
   суточного timestamp с текущим UTC-моментом.
2. Баланс осадки − ET₀ не возвращает фиктивный ноль при отсутствии данных.
   Требуются парные значения, публикуются valid/missing days.
3. ГТК использует только завершённое прошлое окно; прогнозные осадки исключены.
4. Frost screening использует только `forecast` и не выдаётся за вероятность
   повреждения культуры.
5. Удалены синтетические ML prototypes: scripts/train_basic_model.py.

## Научные и эксплуатационные инварианты

- reanalysis, operational past и forecast не смешиваются;
- NaN не превращается в ноль;
- каждый расчёт сообщает единицы, метод, покрытие и пропуски;
- Historical Weather API называется реанализом, а не наблюдением;
- недоступная функция явно выключена в capability matrix;
- schema head, PostgreSQL, Redis, heartbeat и systemd проверяются до readiness.

## Не реализовано и не должно имитироваться

SoilGrids, satellite NDVI/LAI, SPI, прогноз урожайности, локальный FAO-56
Penman–Monteith и crop/phase-specific probability повреждения заморозком.
