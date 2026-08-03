from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.agro.crop_catalog import get_crop_name
from src.api.open_meteo import OpenMeteoError
from src.application.agro_report import generate_agro_report
from src.bot.keyboards import get_field_keyboard, get_main_keyboard
from src.bot.pest_keyboards import get_report_result_with_pests_keyboard
from src.bot.report_presentation import compact_agro_report
from src.bot.telegram_text import answer_html, edit_html
from src.database.crud import get_field_context, update_field_metadata
from src.database.phenology import get_active_crop_phenology
from src.domain.season import local_today

logger = logging.getLogger(__name__)
router = Router(name="report")


async def _generate(session: AsyncSession, telegram_id: int):
    context = await get_field_context(session, telegram_id)
    if context is None:
        raise ValueError("Сначала добавьте поле.")
    phenology = await get_active_crop_phenology(session, telegram_id)
    await session.rollback()
    report = await generate_agro_report(
        context.latitude,
        context.longitude,
        context.crop_key,
        season_start_date=context.season_start_date,
        phenological_phase=context.phenological_phase,
        field_name=context.field_name,
    )
    await update_field_metadata(
        session,
        context.field_id,
        timezone=report.timezone,
        timezone_source=report.metadata_source,
        elevation_m=report.elevation_m,
        elevation_source=report.metadata_source,
    )
    return context, phenology, report


def _compact(context, phenology, report) -> str:
    return compact_agro_report(
        report.text,
        season_start_date=context.season_start_date,
        today=local_today(report.timezone),
        source="Open-Meteo",
        crop_key=context.crop_key,
        current_phase=context.phenological_phase,
        date_basis=(phenology.date_basis if phenology is not None else None),
        phase_confirmed_at=(
            phenology.phase_confirmed_at if phenology is not None else None
        ),
        timezone_name=report.timezone,
    )


@router.callback_query(F.data == "agro_report")
async def agro_report(callback: CallbackQuery, session: AsyncSession) -> None:
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
        f"🌐 Поле <b>{html.escape(context.field_name)}</b>\n"
        f"Культура: <b>{html.escape(get_crop_name(context.crop_key))}</b>\n"
        "Получаю данные, считаю осадки и накопленное тепло…",
    )
    try:
        updated_context, phenology, report = await _generate(
            session,
            callback.from_user.id,
        )
        await edit_html(
            progress,
            _compact(updated_context, phenology, report),
            reply_markup=get_report_result_with_pests_keyboard(),
        )
    except OpenMeteoError:
        logger.warning(
            "Open-Meteo unavailable for user %s field %s",
            callback.from_user.id,
            context.field_id,
        )
        await edit_html(
            progress,
            "⚠️ Метеоданные сейчас недоступны. Бот не заменяет расчёт догадкой; "
            "повторите запрос позже.",
            reply_markup=get_main_keyboard(),
        )
    except Exception:
        logger.exception(
            "Agro report failed for user %s field %s",
            callback.from_user.id,
            context.field_id,
        )
        await edit_html(
            progress,
            "⚠️ Не удалось сформировать отчёт. Ошибка записана в журнал сервиса. "
            "Повторите запрос после обновления данных.",
            reply_markup=get_main_keyboard(),
        )


@router.message(Command("report"))
async def agro_report_command(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    try:
        context, phenology, report = await _generate(session, message.from_user.id)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=get_field_keyboard())
        return
    except OpenMeteoError:
        await message.answer(
            "⚠️ Метеоданные сейчас недоступны. Повторите позже.",
            reply_markup=get_main_keyboard(),
        )
        return
    except Exception:
        logger.exception("Agro report command failed for user %s", message.from_user.id)
        await message.answer(
            "⚠️ Не удалось сформировать отчёт. Ошибка записана в журнал сервиса.",
            reply_markup=get_main_keyboard(),
        )
        return

    await answer_html(
        message,
        _compact(context, phenology, report),
        reply_markup=get_report_result_with_pests_keyboard(),
    )
