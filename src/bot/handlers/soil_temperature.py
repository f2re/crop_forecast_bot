from __future__ import annotations

import html
import logging
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.open_meteo import OpenMeteoError
from src.application.pest_monitoring import PestMonitorRequest, evaluate_pest_monitors
from src.application.soil_temperature import (
    SoilTemperatureReport,
    generate_soil_temperature_report,
)
from src.bot.keyboards import get_field_keyboard, get_main_keyboard
from src.bot.pest_keyboards import get_pest_monitor_keyboard
from src.bot.pest_messages import format_pest_outlook
from src.bot.telegram_text import answer_html, edit_html
from src.database.crud import get_field_context
from src.database.pest_monitoring import (
    get_active_pest_context,
    upsert_pest_monitor,
)
from src.domain.pests import (
    automatic_biofix_date,
    get_pest_model,
    validate_pest_for_crop,
)
from src.domain.season import local_today

logger = logging.getLogger(__name__)
router = Router(name="soil-temperature")

_OPEN_METEO_SOIL_DOCS = "https://open-meteo.com/en/docs/ecmwf-api"


def _soil_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data="soil_temperature",
                ),
                InlineKeyboardButton(
                    text="🐛 Вредители",
                    callback_data="pest_overview",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Что это значит",
                    callback_data="soil_temperature_help",
                ),
                InlineKeyboardButton(
                    text="📚 Источник",
                    url=_OPEN_METEO_SOIL_DOCS,
                ),
            ],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )


def _soil_help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить отчёт",
                    callback_data="soil_temperature",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 Документация Open-Meteo",
                    url=_OPEN_METEO_SOIL_DOCS,
                )
            ],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )


def _format_day(day) -> str:
    return (
        f"{day.local_date:%d.%m}: {day.mean_c:.1f} °C "
        f"({day.minimum_c:.1f}…{day.maximum_c:.1f})"
    )


def _short_source(source: str) -> str:
    has_ecmwf = "ECMWF" in source
    has_era5_land = "ERA5-Land" in source
    if has_ecmwf and has_era5_land:
        return "ERA5-Land и ECMWF через Open-Meteo"
    if has_era5_land:
        return "ERA5-Land через Open-Meteo"
    if has_ecmwf:
        return "ECMWF через Open-Meteo"
    return source


def _format_remaining_forecast(days) -> str:
    start = days[0].local_date
    end = days[-1].local_date
    mean_value = sum(day.mean_c for day in days) / len(days)
    if start == end:
        period = f"{start:%d.%m}"
    else:
        period = f"{start:%d.%m}–{end:%d.%m}"
    return f"{period}: около {mean_value:.1f} °C"


def format_soil_temperature_report(
    report: SoilTemperatureReport,
    *,
    field_name: str,
) -> str:
    lines = [
        "🌡 <b>Почва 0–7 см</b>",
        f"🗺 {html.escape(field_name)}",
        "",
    ]
    if report.latest_completed is None:
        lines.append("За вчера нет полного модельного ряда.")
    else:
        lines.append(
            f"<b>{report.latest_completed.local_date:%d.%m} по модели:</b> "
            f"{report.latest_completed.mean_c:.1f} °C "
            f"({report.latest_completed.minimum_c:.1f}…"
            f"{report.latest_completed.maximum_c:.1f})"
        )

    if report.recent_change_c is not None and report.recent_days >= 2:
        if abs(report.recent_change_c) < 0.5:
            trend = "почти без изменений"
        elif report.recent_change_c > 0:
            trend = f"потепление на {report.recent_change_c:.1f} °C"
        else:
            trend = f"похолодание на {abs(report.recent_change_c):.1f} °C"
        lines.append(f"За {report.recent_days} дня: {trend}.")

    lines.extend(["", "<b>Сегодня и далее</b>"])
    if not report.forecast:
        lines.append("Прогноз сейчас недоступен.")
    else:
        for day in report.forecast[:4]:
            lines.append(f"• {_format_day(day)}")
        remaining = report.forecast[4:]
        if remaining:
            lines.append(f"• {_format_remaining_forecast(remaining)}")

    local_retrieved = report.retrieved_at.astimezone(ZoneInfo(report.timezone))
    timezone_label = local_retrieved.tzname() or report.timezone
    lines.extend(
        [
            "",
            "ℹ️ Модель, не датчик: на поле температура может отличаться.",
            f"Источник: {html.escape(_short_source(report.source))} · "
            f"{local_retrieved:%d.%m %H:%M} {html.escape(timezone_label)}.",
        ]
    )
    return "\n".join(lines)


def format_soil_temperature_help() -> str:
    return "\n".join(
        [
            "ℹ️ <b>Что показывает бот</b>",
            "Среднюю температуру верхнего модельного слоя почвы 0–7 см. "
            "Суточные минимум, максимум и среднее рассчитаны из почасовых значений.",
            "",
            "<b>Откуда данные</b>",
            "• ECMWF IFS через Open-Meteo.",
            "• Модель обновляется до 4 раз в сутки; ответ бота хранится не более часа.",
            "• Значение за вчера — архив модели, а не измерение метеостанции.",
            "• Точную выбранную сетку API не сообщает; доступные расчёты ECMWF "
            "имеют шаг примерно 9–28 км.",
            "",
            "<b>Как использовать</b>",
            "• Смотреть общий прогрев или охлаждение верхнего слоя.",
            "• Применять только пороги конкретной культуры или проверенной модели "
            "вредителя.",
            "• Перед посевом или обработкой измерить почву на рабочей глубине "
            "в нескольких точках поля.",
            "",
            "Влажность, растительный покров, рельеф, тип и обработка почвы могут "
            "заметно изменить фактическую температуру.",
        ]
    )


async def _generate_for_user(
    session: AsyncSession,
    telegram_id: int,
) -> tuple[object, SoilTemperatureReport]:
    context = await get_field_context(session, telegram_id)
    if context is None:
        raise ValueError("Сначала добавьте поле.")
    await session.rollback()
    report = await generate_soil_temperature_report(
        context.latitude,
        context.longitude,
    )
    return context, report


@router.callback_query(F.data == "soil_temperature")
async def soil_temperature_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await edit_html(
            callback.message,
            "Сначала добавьте поле.",
            reply_markup=get_field_keyboard(),
        )
        return

    progress = callback.message
    await edit_html(
        progress,
        f"🌡 Поле <b>{html.escape(context.field_name)}</b>\n"
        "Получаю температуру почвы…",
    )
    try:
        _, report = await _generate_for_user(session, callback.from_user.id)
    except OpenMeteoError:
        await edit_html(
            progress,
            "⚠️ Температура почвы сейчас недоступна. Бот не заменяет пропуск "
            "температурой воздуха; повторите запрос позже.",
            reply_markup=get_main_keyboard(),
        )
        return
    except Exception:
        logger.exception(
            "Soil-temperature report failed for user %s",
            callback.from_user.id,
        )
        await edit_html(
            progress,
            "⚠️ Не удалось сформировать отчёт о температуре почвы. "
            "Ошибка записана в журнал сервиса.",
            reply_markup=get_main_keyboard(),
        )
        return

    await edit_html(
        progress,
        format_soil_temperature_report(report, field_name=context.field_name),
        reply_markup=_soil_keyboard(),
    )


@router.callback_query(F.data == "soil_temperature_help")
async def soil_temperature_help_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        format_soil_temperature_help(),
        reply_markup=_soil_help_keyboard(),
    )


@router.message(Command("soil"))
async def soil_temperature_command(
    message: Message,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        return
    try:
        context, report = await _generate_for_user(session, message.from_user.id)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=get_field_keyboard())
        return
    except OpenMeteoError:
        await message.answer(
            "⚠️ Температура почвы сейчас недоступна. Повторите запрос позже.",
            reply_markup=get_main_keyboard(),
        )
        return
    except Exception:
        logger.exception(
            "Soil-temperature command failed for user %s",
            message.from_user.id,
        )
        await message.answer(
            "⚠️ Не удалось сформировать отчёт о температуре почвы.",
            reply_markup=get_main_keyboard(),
        )
        return

    await answer_html(
        message,
        format_soil_temperature_report(report, field_name=context.field_name),
        reply_markup=_soil_keyboard(),
    )


@router.callback_query(F.data == "pest_setup:seedcorn_maggot_soil")
async def enable_seedcorn_maggot_calendar_model(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """Enable the published January-1 soil model without asking for a fake find."""

    model = get_pest_model("seedcorn_maggot_soil")
    context = await get_active_pest_context(
        session,
        callback.from_user.id,
        model.key,
    )
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    try:
        validate_pest_for_crop(model.key, context.crop_key)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    today = local_today(context.timezone)
    biofix = automatic_biofix_date(model, today)
    if biofix is None:
        await callback.answer(
            "Для модели не задано календарное начало",
            show_alert=True,
        )
        return
    saved = await upsert_pest_monitor(
        session,
        callback.from_user.id,
        pest_key=model.key,
        biofix_date=biofix,
    )
    await callback.answer("Расчёт включён с 1 января")
    if callback.message is None:
        return

    try:
        result = (
            await evaluate_pest_monitors(
                saved.latitude,
                saved.longitude,
                (
                    PestMonitorRequest(
                        monitor_id=saved.monitor_id,
                        pest_key=model.key,
                        biofix_date=biofix,
                    ),
                ),
            )
        )[0]
    except OpenMeteoError:
        await edit_html(
            callback.message,
            "✅ Наблюдение сохранено с 1 января. Температурный ряд почвы "
            "сейчас недоступен; бот повторит расчёт позже.",
            reply_markup=get_pest_monitor_keyboard(
                model,
                configured=True,
                enabled=True,
            ),
        )
        return

    await edit_html(
        callback.message,
        format_pest_outlook(
            result.outlook,
            field_name=saved.field_name,
            crop_key=saved.crop_key,
            source=result.source,
        ),
        reply_markup=get_pest_monitor_keyboard(
            model,
            configured=True,
            enabled=True,
        ),
    )
