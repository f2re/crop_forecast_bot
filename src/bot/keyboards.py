from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.settings import get_settings
from src.agro.crop_catalog import CATEGORIES, CROPS, get_crop_name, get_crop_phases
from src.domain.risk_delivery import quiet_hours_label, risk_delivery_mode_label


class FieldKeyboardItem(Protocol):
    field_id: int
    field_name: str
    crop_key: str
    is_active: bool


def get_main_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🌦 Агроотчёт", callback_data="agro_report")],
        [InlineKeyboardButton(text="⚠️ Погодные условия", callback_data="risk_overview")],
        [
            InlineKeyboardButton(
                text="🕘 История предупреждений",
                callback_data="risk_history",
            )
        ],
        [InlineKeyboardButton(text="🗺 Мои поля", callback_data="fields")],
        [InlineKeyboardButton(text="🌱 Культуры поля", callback_data="crop_choose")],
        [InlineKeyboardButton(text="📅 Дата и стадия", callback_data="season")],
    ]
    if get_settings().rag_enabled:
        rows.append(
            [InlineKeyboardButton(text="🤖 Агросоветник", callback_data="agro_advisor")]
        )
    rows.append(
        [InlineKeyboardButton(text="⚙️ Уведомления", callback_data="settings")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_field_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for the first field in an empty profile."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⌨️ Ввести координаты", callback_data="field_manual")],
            [
                InlineKeyboardButton(
                    text="📱 Отправить геолокацию",
                    callback_data="field_location",
                )
            ],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )


def get_fields_keyboard(fields: Sequence[FieldKeyboardItem]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for field in fields:
        marker = "✅" if field.is_active else "▫️"
        crop_name = get_crop_name(field.crop_key)
        label = f"{marker} {field.field_name} · выбрано: {crop_name}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"field_open:{field.field_id}",
                )
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="➕ Добавить поле", callback_data="field_add")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_field_actions_keyboard(
    field_id: int,
    *,
    is_active: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not is_active:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Сделать активным",
                    callback_data=f"field_activate:{field_id}",
                )
            ]
        )
    else:
        rows.extend(
            [
                [InlineKeyboardButton(text="🌦 Агроотчёт", callback_data="agro_report")],
                [
                    InlineKeyboardButton(
                        text="⚠️ Погодные условия",
                        callback_data="risk_overview",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🕘 История предупреждений",
                        callback_data="risk_history",
                    )
                ],
                [InlineKeyboardButton(text="🌱 Культуры поля", callback_data="crop_choose")],
                [InlineKeyboardButton(text="📅 Дата и стадия", callback_data="season")],
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="✏️ Переименовать",
                    callback_data=f"field_rename:{field_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⌨️ Изменить координаты",
                    callback_data=f"field_update_manual:{field_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📱 Новая геолокация",
                    callback_data=f"field_update_location:{field_id}",
                )
            ],
            [InlineKeyboardButton(text="◀️ К списку полей", callback_data="fields")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_new_field_coordinate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⌨️ Ввести координаты",
                    callback_data="field_create_manual",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📱 Отправить геолокацию",
                    callback_data="field_create_location",
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="fields")],
        ]
    )


def get_location_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Отправьте геолокацию или нажмите «Отмена»",
    )


def get_crop_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category_id, category in CATEGORIES.items():
        builder.button(
            text=f"{category['emoji']} {category['label']}",
            callback_data=f"crop_cat:{category_id}",
        )
    builder.button(text="◀️ В меню", callback_data="menu")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def get_crop_list_keyboard(category_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    category = CATEGORIES.get(category_id)
    if category:
        for crop_key in category["crops"]:
            crop = CROPS.get(str(crop_key))
            if crop:
                builder.button(
                    text=f"{crop['emoji']} {crop['name_ru']}",
                    callback_data=f"crop_pick:{crop_key}",
                )
    builder.button(text="◀️ К категориям", callback_data="crop_choose")
    builder.adjust(2)
    return builder.as_markup()


def get_season_keyboard(*, has_start: bool, has_phase: bool) -> InlineKeyboardMarkup:
    date_action = "Изменить дату" if has_start else "Выбрать дату посева"
    rows = [
        [InlineKeyboardButton(text=f"📅 {date_action}", callback_data="season_start_set")],
        [
            InlineKeyboardButton(
                text="🌿 Указать фактическую стадию",
                callback_data="season_phase",
            )
        ],
        [InlineKeyboardButton(text="🌱 Культуры поля", callback_data="crop_choose")],
    ]
    if has_phase:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🧹 Удалить указанную стадию",
                    callback_data="phase_clear",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_phase_keyboard(crop_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, phase in enumerate(get_crop_phases(crop_key)):
        builder.button(text=phase, callback_data=f"phase_pick:{index}")
    builder.button(text="◀️ К дате и стадии", callback_data="season")
    builder.adjust(1)
    return builder.as_markup()


def get_report_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌡 Как считается тепло",
                    callback_data="report_help:heat",
                ),
                InlineKeyboardButton(
                    text="💧 Как считаются осадки",
                    callback_data="report_help:water",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🌦 Что такое ГТК",
                    callback_data="report_help:htc",
                ),
                InlineKeyboardButton(
                    text="🌿 Почему стадия не меняется",
                    callback_data="report_help:phase",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🧾 Источники и точность",
                    callback_data="report_help:sources",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌿 Уточнить стадию",
                    callback_data="season_phase",
                )
            ],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )


def get_risk_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ℹ️ Как читать варианты прогноза",
                    callback_data="report_help:risk",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌿 Уточнить стадию",
                    callback_data="season_phase",
                )
            ],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )


def get_report_help_keyboard(*, back_callback: str) -> InlineKeyboardMarkup:
    back_label = (
        "◀️ К погодным условиям"
        if back_callback == "risk_overview"
        else "◀️ К отчёту"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=back_label, callback_data=back_callback)],
            [
                InlineKeyboardButton(
                    text="🌿 Уточнить стадию",
                    callback_data="season_phase",
                )
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        ]
    )


def get_settings_keyboard(
    *,
    daily_digest_enabled: bool,
    frost_alerts_enabled: bool,
    field_id: int | None = None,
    risk_delivery_mode: str = "immediate",
    quiet_hours_start: int | None = None,
    quiet_hours_end: int | None = None,
) -> InlineKeyboardMarkup:
    """Build replay-safe notification controls for one field."""
    digest_action = "Отключить" if daily_digest_enabled else "Включить"
    risk_action = "Отключить" if frost_alerts_enabled else "Включить"
    if field_id is None:
        digest_callback = "settings"
        risk_callback = "settings"
        mode_callback = "settings"
        quiet_callback = "settings"
    else:
        digest_callback = (
            f"set_digest:{field_id}:{0 if daily_digest_enabled else 1}"
        )
        risk_callback = (
            f"set_frost:{field_id}:{0 if frost_alerts_enabled else 1}"
        )
        mode_callback = f"risk_mode_menu:{field_id}"
        quiet_callback = f"quiet_hours_menu:{field_id}"
    mode_label = risk_delivery_mode_label(risk_delivery_mode)
    quiet_label = quiet_hours_label(quiet_hours_start, quiet_hours_end)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{digest_action} ежедневный агроотчёт",
                    callback_data=digest_callback,
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{risk_action} предупреждения о погоде",
                    callback_data=risk_callback,
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Как присылать предупреждения: {mode_label}",
                    callback_data=mode_callback,
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Тихие часы: {quiet_label}",
                    callback_data=quiet_callback,
                )
            ],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )


def get_risk_delivery_mode_keyboard(
    field_id: int,
    current_mode: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    options = (
        ("immediate", "Сразу при новом предупреждении"),
        ("digest", "Одна сводка в сутки"),
        ("high_only", "Только важные предупреждения"),
    )
    for mode, label in options:
        marker = "✅ " if mode == current_mode else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker}{label}",
                    callback_data=f"set_risk_mode:{field_id}:{mode}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ К настройкам", callback_data="settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_quiet_hours_keyboard(
    field_id: int,
    start_hour: int | None,
    end_hour: int | None,
) -> InlineKeyboardMarkup:
    current = (start_hour, end_hour)
    options = (
        ("off", None, None, "Выключить"),
        ("22-07", 22, 7, "22:00–07:00"),
        ("23-06", 23, 6, "23:00–06:00"),
    )
    rows: list[list[InlineKeyboardButton]] = []
    for token, start, end, label in options:
        marker = "✅ " if current == (start, end) else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker}{label}",
                    callback_data=f"set_quiet_hours:{field_id}:{token}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ К настройкам", callback_data="settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_rag_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_rag")],
        ]
    )
