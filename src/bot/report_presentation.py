from __future__ import annotations

import html
import re
from datetime import date, datetime

from src.domain.phenology import date_basis_label, evaluate_stage_review

_NUMBER = r"([+-]?\d+(?:\.\d+)?)"


def _find_line(lines: list[str], prefix: str) -> str | None:
    return next((line for line in lines if line.startswith(prefix)), None)


def _water_difference(days: int, value: float) -> str:
    magnitude = abs(value)
    if value < 0:
        relation = f"осадков было на <b>{magnitude:.1f} мм меньше</b>"
    elif value > 0:
        relation = f"осадков было на <b>{magnitude:.1f} мм больше</b>"
    else:
        relation = "суммы осадков и эталонного испарения были почти равны"
    return (
        f"• За {days} завершённых суток {relation}, чем эталонного "
        "испарения. Это не запас воды в почве."
    )


def _stage_review_lines(
    *,
    crop_key: str,
    current_phase: str | None,
    phase_confirmed_at: datetime | None,
    today: date,
    timezone_name: str,
) -> list[str]:
    review = evaluate_stage_review(
        crop_key,
        current_phase=current_phase,
        phase_confirmed_at=phase_confirmed_at,
        today=today,
        timezone_name=timezone_name,
    )
    if not review.needs_review:
        return []
    if review.status == "stage_missing":
        return [
            "🔔 Фактическая стадия ещё не подтверждена. Осмотрите растения и "
            "укажите её кнопкой ниже."
        ]
    if review.status == "confirmation_time_unknown":
        next_note = (
            f" При осмотре обратите внимание на следующую стадию: "
            f"<b>{html.escape(review.next_stage)}</b>."
            if review.next_stage
            else ""
        )
        return [
            "🔔 Дата последнего подтверждения стадии неизвестна. "
            f"Проверьте наблюдение.{next_note}",
            "ℹ️ Это напоминание по давности записи, а не расчёт стадии.",
        ]
    if review.status == "stage_not_in_catalog":
        return [
            "🔔 Сохранённая стадия не входит в текущий справочник культуры. "
            "Выберите её повторно после осмотра."
        ]
    if review.days_since_confirmation is None:
        return []
    if review.next_stage:
        action = (
            "При осмотре проверьте, не появилась ли следующая стадия: "
            f"<b>{html.escape(review.next_stage)}</b>."
        )
    else:
        action = "Проверьте состояние растений и завершение текущего сезона."
    return [
        f"🔔 Стадия подтверждена <b>{review.days_since_confirmation} сут.</b> "
        f"назад. {action}",
        "ℹ️ Это календарное напоминание, а не автоматическое определение стадии.",
    ]


def compact_agro_report(
    text: str,
    *,
    season_start_date: date | None = None,
    today: date | None = None,
    source: str | None = None,
    crop_key: str | None = None,
    current_phase: str | None = None,
    date_basis: str | None = None,
    phase_confirmed_at: datetime | None = None,
    timezone_name: str = "UTC",
) -> str:
    """Turn the full diagnostic report into a short farmer-facing summary.

    The calculation layer remains unchanged. This function only selects and
    renames already calculated values, removing internal provider and dataframe
    vocabulary from the primary Telegram message. Detailed method explanations
    are available from inline buttons attached by the report handler.
    """

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    recognized = any(
        line.startswith(
            (
                "🗺 Поле:",
                "🌱 Культура:",
                "• ГДД ",
                "• Накопленные осадки ",
            )
        )
        for line in lines
    )
    if not recognized:
        return text

    result: list[str] = ["🌾 <b>Отчёт по полю</b>"]

    for prefix in ("🗺 Поле:", "🌱 Культура:"):
        line = _find_line(lines, prefix)
        if line:
            result.append(line)

    date_line = _find_line(lines, "📅 Начало сезона/посев:")
    if date_line:
        label = date_basis_label(date_basis).capitalize()
        result.append(date_line.replace("📅 Начало сезона/посев:", f"📅 {label}:"))

    phase_line = _find_line(lines, "🌿 Фаза:")
    if phase_line:
        result.append(
            phase_line.replace("Фаза:", "Стадия:").replace(
                " — указана пользователем",
                " — подтверждена пользователем",
            )
        )

    if crop_key is not None and today is not None:
        result.extend(
            _stage_review_lines(
                crop_key=crop_key,
                current_phase=current_phase,
                phase_confirmed_at=phase_confirmed_at,
                today=today,
                timezone_name=timezone_name,
            )
        )
    elif (
        season_start_date is not None
        and today is not None
        and today >= season_start_date
    ):
        age_days = (today - season_start_date).days
        result.append(
            f"🔔 С указанной даты прошло <b>{age_days} сут.</b> Проверьте, "
            "соответствует ли выбранная стадия фактическому состоянию растений."
        )

    main: list[str] = []
    checked_days: int | None = None
    checked_line = _find_line(lines, "• Проверено прогнозных суток:")
    if checked_line:
        match = re.search(r"(\d+)$", checked_line)
        if match:
            checked_days = int(match.group(1))

    if any("Температурный риск не оценён" in line for line in lines):
        main.append("⚠️ Похолодание не оценено: в прогнозе не хватает данных.")
    elif any("есть температурный риск" in line for line in lines):
        main.append("🌡 Есть общий погодный признак опасного похолодания.")
        for line in lines:
            if re.match(r"• \d{2}\.\d{2}\.\d{4}: Tmin воздуха", line):
                main.append(
                    line.replace(
                        "Tmin воздуха",
                        "минимальная температура воздуха",
                    )
                )
    elif any(
        "температурный риск по заданной политике не выявлен" in line
        for line in lines
    ):
        suffix = f" по {checked_days} проверенным суткам" if checked_days else ""
        main.append(
            "✅ Общий порог предупреждения о холоде"
            f"{suffix} не достигнут."
        )

    htc_pattern = re.compile(
        rf"^• ГТК = {_NUMBER};.*тёплых валидных суток: (\d+)\)$"
    )
    for line in lines:
        match = htc_pattern.match(line)
        if match:
            main.append(
                f"• Показатель увлажнения (ГТК): "
                f"<b>{float(match.group(1)):.2f}</b> "
                f"по {int(match.group(2))} тёплым суткам."
            )
            break

    balance_pattern = re.compile(
        rf"^• Осадки − ET₀ за (\d+) завершённых суток: {_NUMBER} мм\."
    )
    for line in lines:
        match = balance_pattern.match(line)
        if match:
            main.append(
                _water_difference(
                    int(match.group(1)),
                    float(match.group(2)),
                )
            )
            break

    precip_pattern = re.compile(
        rf"^• Накопленные осадки "
        rf"(с начала сезона|за доступный завершённый период): "
        rf"{_NUMBER} мм по (\d+) валидным суткам\.$"
    )
    for line in lines:
        match = precip_pattern.match(line)
        if match:
            scope = (
                "С начала сезона"
                if match.group(1) == "с начала сезона"
                else "За доступный период"
            )
            main.append(
                f"• {scope} выпало <b>{float(match.group(2)):.1f} мм</b> осадков "
                f"({int(match.group(3))} суток с данными)."
            )
            break

    dry_pattern = re.compile(
        r"^• Сухая серия на конец ряда: (\d+) сут\.; максимум (\d+) сут\. "
        r"при осадках <[\d.]+ мм/сут\.$"
    )
    for line in lines:
        match = dry_pattern.match(line)
        if match:
            main.append(
                f"• Без заметных осадков: <b>{int(match.group(1))} сут.</b>; "
                f"самая длинная серия — {int(match.group(2))} сут."
            )
            break

    gdd_pattern = re.compile(
        rf"^• ГДД (с начала сезона|за доступный период): {_NUMBER}°C·сут "
        rf"при Tbase={_NUMBER}°C$"
    )
    for line in lines:
        match = gdd_pattern.match(line)
        if match:
            scope = (
                "С начала сезона"
                if match.group(1) == "с начала сезона"
                else "За доступный период"
            )
            main.append(
                f"• {scope} накоплено <b>{float(match.group(2)):.1f} °C·сут</b> "
                f"тепла; базовая температура — {float(match.group(3)):.1f} °C."
            )
            break

    forecast_gdd_pattern = re.compile(
        rf"^• Прогнозный прирост за (\d+) сут\.: {_NUMBER}°C·сут$"
    )
    for line in lines:
        match = forecast_gdd_pattern.match(line)
        if match:
            main.append(
                f"• За ближайшие {int(match.group(1))} сут. ожидается ещё "
                f"<b>{float(match.group(2)):.1f} °C·сут</b>."
            )
            break

    if main:
        result.extend(["", "<b>Главное</b>", *main])

    climate_unavailable = next(
        (
            line
            for line in lines
            if line.startswith("• Не рассчитано:")
            and ("ERA5" in line or "однородный ряд" in line)
        ),
        None,
    )
    if climate_unavailable:
        result.extend(
            [
                "",
                "📊 <b>Сравнение с 1991–2020</b>",
                "• Пока недоступно. Основные показатели выше рассчитаны "
                "без этого блока.",
            ]
        )

    result.extend(["", "🧾 <b>Данные</b>"])
    source_label = html.escape(source) if source else "Open-Meteo"
    result.append(
        f"• Источник: {source_label}. Прошлые сутки — расчётный архив; "
        "ближайшие дни — прогноз."
    )
    retrieved_line = _find_line(lines, "• Получено ботом:")
    if retrieved_line:
        result.append(
            retrieved_line.replace("• Получено ботом:", "• Обновлено:").replace(
                " UTC",
                " по всемирному времени",
            )
        )
    result.append("• Подробные формулы, примеры и ограничения — в кнопках ниже.")

    compact = "\n".join(result)
    if len(compact) > 4096:
        return text
    return compact
