from __future__ import annotations

import html
import logging
from datetime import timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
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
                    text="📚 Описание источника",
                    url=_OPEN_METEO_SOIL_DOCS,
                )
            ],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )


def _format_day(day) -> str:
    return (
        f"{day.local_date:%d.%m}: средняя {day.mean_c:.1f} °C "
        f"(от {day.minimum_c:.1f} до {day.maximum_c:.1f} °C)"
    )


def format_soil_temperature_report(
    report: SoilTemperatureReport,
    *,
    field_name: str,
) -> str:
    lines = [
        "🌡 <b>Температура почвы</b>",
        f"🗺 Поле: {html.escape(field_name)}",
        f"📏 Глубина: {html.escape(report.depth_label)}",
        "",
    ]
    if report.latest_completed is None:
        lines.append("• Нет полностью завершённых суток для фактического итога.")
    else:
        lines.extend(
            [
                "<b>Последние завершённые сутки</b>",
                f"• {_format_day(report.latest_completed)}.",
            ]
        )
    if report.recent_mean_c is not None:
        change = ""
        if report.recent_change_c is not None:
            direction = "выше" if report.recent_change_c > 0 else "ниже"
            if report.recent_change_c == 0:
                change = "; без заметного изменения"
            else:
                change = (
                    f"; к концу периода на {abs(report.recent_change_c):.1f} °C "
                    f"{direction}"
                )
        lines.append(
            f"• Средняя за {report.recent_days} завершённых сут.: "
            f"{report.recent_mean_c:.1f} °C{change}."
        )

    lines.extend(["", "<b>Ближайшие дни по модели</b>"])
    if not report.forecast:
        lines.append("• Прогнозный ряд отсутствует.")
    else:
        for day in report.forecast[:5]:
            lines.append(f"• {_format_day(day)}.")
        if len(report.forecast) > 5:
            remaining = report.forecast[5:]
            mean_value = sum(day.mean_c for day in remaining) / len(remaining)
            lines.append(
                f"• Ещё {len(remaining)} сут.: средняя около {mean_value:.1f} °C."
            )

    retrieved = report.retrieved_at.astimezone(timezone.utc)
    resolution = (
        "не указано"
        if report.spatial_resolution_km is None
        else f"около {report.spatial_resolution_km:g} км"
    )
    lines.extend(
        [
            "",
            "<b>Как читать</b>",
            "• Это средняя температура модельного слоя 0–7 см, а не показание "
            "датчика на глубине посева.",
            "• Влажность, растительный покров, обработка почвы, снег и местный "
            "рельеф могут давать заметное отличие на поле.",
            "• Универсальный вывод «можно сеять» по одному числу не формируется. "
            "Порог должен относиться к конкретной культуре или опубликованной "
            "модели вредителя.",
            "",
            f"Источник: {html.escape(report.source)}.",
            f"Сетка: {resolution}; получено {retrieved:%d.%m.%Y %H:%M UTC}.",
        ]
    )
    return "\n".join(lines)


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

    progress = await answer_html(
        callback.message,
        f"🌡 Поле <b>{html.escape(context.field_name)}</b>\n"
        "Получаю температуру модельного слоя почвы 0–7 см…",
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
        await callback.answer("Для модели не задано календарное начало", show_alert=True)
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
