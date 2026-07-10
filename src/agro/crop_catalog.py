"""Crop catalogue used by Telegram UX and GDD parameter selection.

The catalogue contains names, user-selectable observed phase labels and an
*operational default* GDD base temperature. It intentionally contains no
automatic phase thresholds, yield targets, suitability scores or damage
thresholds.

Base temperature is a model parameter rather than an observation. Cultivar,
production system and regional guidance may require a different value; reports
must display the value and its source.
"""
from __future__ import annotations

from typing import Any

_DEFAULT_TBASE_SOURCE = (
    "operational crop-catalogue default; verify cultivar and regional guidance"
)

CATEGORIES: dict[str, dict[str, Any]] = {
    "grains": {
        "label": "Зерновые",
        "emoji": "🌾",
        "crops": ["wheat", "barley", "oat", "rye", "triticale", "sorghum"],
    },
    "corn_cereals": {
        "label": "Кукуруза / крупы",
        "emoji": "🌽",
        "crops": ["corn", "millet", "buckwheat", "rice"],
    },
    "oilseeds": {
        "label": "Масличные",
        "emoji": "🌻",
        "crops": ["sunflower", "rapeseed", "flax", "soy", "mustard"],
    },
    "root_crops": {
        "label": "Корнеплоды",
        "emoji": "🥔",
        "crops": ["potato", "sugarbeet", "carrot", "beet"],
    },
    "vegetables": {
        "label": "Овощи / бахчевые",
        "emoji": "🍅",
        "crops": [
            "tomato",
            "cucumber",
            "zucchini",
            "watermelon",
            "melon",
            "onion",
            "garlic",
        ],
    },
    "forage": {
        "label": "Кормовые",
        "emoji": "🌿",
        "crops": ["alfalfa", "clover", "timothy", "corn_silage"],
    },
}


def _crop(
    name_ru: str,
    emoji: str,
    t_base: float,
    category: str,
    phases: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "name_ru": name_ru,
        "emoji": emoji,
        "t_base": float(t_base),
        "t_base_source": _DEFAULT_TBASE_SOURCE,
        "category": category,
        "phases": phases,
        # Compatibility for the current keyboard API. Values are deliberately
        # None: they are labels for manual observations, not GDD thresholds.
        "gdd_stages": {phase: None for phase in phases},
    }


CROPS: dict[str, dict[str, Any]] = {
    "wheat": _crop(
        "Пшеница",
        "🌾",
        5.0,
        "grains",
        (
            "Всходы",
            "Кущение",
            "Выход в трубку",
            "Колошение",
            "Молочная спелость",
            "Полная спелость",
        ),
    ),
    "barley": _crop(
        "Ячмень",
        "🌾",
        5.0,
        "grains",
        ("Всходы", "Кущение", "Выход в трубку", "Колошение", "Полная спелость"),
    ),
    "oat": _crop(
        "Овёс",
        "🌾",
        4.0,
        "grains",
        ("Всходы", "Кущение", "Выметывание", "Полная спелость"),
    ),
    "rye": _crop(
        "Рожь",
        "🌾",
        5.0,
        "grains",
        ("Всходы", "Кущение", "Колошение", "Полная спелость"),
    ),
    "triticale": _crop(
        "Тритикале",
        "🌾",
        5.0,
        "grains",
        ("Всходы", "Кущение", "Колошение", "Полная спелость"),
    ),
    "sorghum": _crop(
        "Сорго",
        "🌾",
        10.0,
        "grains",
        ("Всходы", "Выметывание", "Полная спелость"),
    ),
    "corn": _crop(
        "Кукуруза",
        "🌽",
        10.0,
        "corn_cereals",
        ("Всходы", "6 листьев", "Выметывание", "Молочная спелость", "Полная спелость"),
    ),
    "millet": _crop(
        "Просо",
        "🌾",
        10.0,
        "corn_cereals",
        ("Всходы", "Выметывание", "Полная спелость"),
    ),
    "buckwheat": _crop(
        "Гречиха",
        "🌿",
        8.0,
        "corn_cereals",
        ("Всходы", "Цветение", "Полная спелость"),
    ),
    "rice": _crop(
        "Рис",
        "🍚",
        10.0,
        "corn_cereals",
        ("Всходы", "Выметывание", "Полная спелость"),
    ),
    "sunflower": _crop(
        "Подсолнечник",
        "🌻",
        6.0,
        "oilseeds",
        ("Всходы", "Бутонизация", "Цветение", "Полная спелость"),
    ),
    "rapeseed": _crop(
        "Рапс",
        "🌼",
        5.0,
        "oilseeds",
        ("Всходы", "Розетка", "Стеблевание", "Цветение", "Полная спелость"),
    ),
    "flax": _crop(
        "Лён",
        "🌿",
        5.0,
        "oilseeds",
        ("Всходы", "Ёлочка", "Бутонизация", "Цветение", "Полная спелость"),
    ),
    "soy": _crop(
        "Соя",
        "🫘",
        10.0,
        "oilseeds",
        ("Всходы", "Ветвление", "Цветение", "Налив бобов", "Полная спелость"),
    ),
    "mustard": _crop(
        "Горчица",
        "🌼",
        5.0,
        "oilseeds",
        ("Всходы", "Розетка", "Цветение", "Полная спелость"),
    ),
    "potato": _crop(
        "Картофель",
        "🥔",
        7.0,
        "root_crops",
        ("Посадка", "Всходы", "Бутонизация", "Цветение", "Отмирание ботвы"),
    ),
    "sugarbeet": _crop(
        "Сахарная свёкла",
        "🥕",
        5.0,
        "root_crops",
        ("Всходы", "Формирование розетки", "Смыкание рядов", "Техническая спелость"),
    ),
    "carrot": _crop(
        "Морковь",
        "🥕",
        5.0,
        "root_crops",
        ("Всходы", "Формирование розетки", "Рост корнеплода", "Техническая спелость"),
    ),
    "beet": _crop(
        "Свёкла столовая",
        "🟣",
        5.0,
        "root_crops",
        ("Всходы", "Формирование розетки", "Рост корнеплода", "Техническая спелость"),
    ),
    "tomato": _crop(
        "Томат",
        "🍅",
        10.0,
        "vegetables",
        ("Всходы", "Бутонизация", "Цветение", "Плодоношение"),
    ),
    "cucumber": _crop(
        "Огурец",
        "🥒",
        10.0,
        "vegetables",
        ("Всходы", "Формирование плетей", "Цветение", "Плодоношение"),
    ),
    "zucchini": _crop(
        "Кабачок",
        "🥒",
        10.0,
        "vegetables",
        ("Всходы", "Формирование листьев", "Цветение", "Плодоношение"),
    ),
    "watermelon": _crop(
        "Арбуз",
        "🍉",
        10.0,
        "vegetables",
        ("Всходы", "Формирование плетей", "Цветение", "Рост плодов", "Полная спелость"),
    ),
    "melon": _crop(
        "Дыня",
        "🍈",
        10.0,
        "vegetables",
        ("Всходы", "Формирование плетей", "Цветение", "Рост плодов", "Полная спелость"),
    ),
    "onion": _crop(
        "Лук",
        "🧅",
        5.0,
        "vegetables",
        ("Всходы", "Рост листьев", "Формирование луковицы", "Полегание листьев"),
    ),
    "garlic": _crop(
        "Чеснок",
        "🧄",
        5.0,
        "vegetables",
        ("Всходы", "Рост листьев", "Формирование луковицы", "Полная спелость"),
    ),
    "alfalfa": _crop(
        "Люцерна",
        "🌿",
        5.0,
        "forage",
        ("Всходы", "Ветвление", "Бутонизация", "Цветение"),
    ),
    "clover": _crop(
        "Клевер",
        "☘️",
        5.0,
        "forage",
        ("Всходы", "Ветвление", "Бутонизация", "Цветение"),
    ),
    "timothy": _crop(
        "Тимофеевка",
        "🌿",
        5.0,
        "forage",
        ("Всходы", "Кущение", "Выход в трубку", "Выметывание"),
    ),
    "corn_silage": _crop(
        "Кукуруза на силос",
        "🌽",
        10.0,
        "forage",
        ("Всходы", "6 листьев", "Выметывание", "Молочная спелость"),
    ),
}


def get_crop(crop_key: str) -> dict[str, Any]:
    """Return a crop definition, falling back to wheat for legacy keys."""

    return CROPS.get(crop_key, CROPS["wheat"])


def get_crop_name(crop_key: str) -> str:
    """Return a Russian crop name."""

    return str(get_crop(crop_key)["name_ru"])


def get_crop_phases(crop_key: str) -> tuple[str, ...]:
    """Return labels allowed for a manual field observation."""

    return tuple(get_crop(crop_key).get("phases", ()))
