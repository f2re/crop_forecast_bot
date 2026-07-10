"""Supported crops and transparent GDD parameters.

The catalogue contains no yield, suitability, pesticide, fertiliser or economic
coefficients. ``t_base`` values are operational reference parameters for the
simple daily-average GDD method. They are not a cultivar/region validation and
must never be used to infer phenological stage automatically.

``phases`` are labels for a user's direct field observation. They deliberately
contain no numeric GDD thresholds.
"""
from __future__ import annotations

from typing import TypedDict


class CropDefinition(TypedDict):
    name_ru: str
    emoji: str
    category: str
    t_base: float
    t_upper: float | None
    phases: tuple[str, ...]


CATEGORIES: dict[str, dict[str, object]] = {
    "grains": {
        "label": "Зерновые",
        "emoji": "🌾",
        "crops": ("wheat", "barley", "oat", "rye", "triticale", "sorghum"),
    },
    "corn_cereals": {
        "label": "Кукуруза / крупы",
        "emoji": "🌽",
        "crops": ("corn", "millet", "buckwheat", "rice"),
    },
    "oilseeds": {
        "label": "Масличные и бобовые",
        "emoji": "🌻",
        "crops": ("sunflower", "rapeseed", "flax", "soy", "mustard"),
    },
    "root_crops": {
        "label": "Корнеплоды",
        "emoji": "🥔",
        "crops": ("potato", "sugarbeet", "carrot", "beet"),
    },
    "vegetables": {
        "label": "Овощи / бахчевые",
        "emoji": "🍅",
        "crops": (
            "tomato",
            "cucumber",
            "zucchini",
            "watermelon",
            "melon",
            "onion",
            "garlic",
        ),
    },
    "forage": {
        "label": "Кормовые",
        "emoji": "🌿",
        "crops": ("alfalfa", "clover", "timothy", "corn_silage"),
    },
}


def _crop(
    name_ru: str,
    emoji: str,
    category: str,
    t_base: float,
    phases: tuple[str, ...],
    *,
    t_upper: float | None = None,
) -> CropDefinition:
    return {
        "name_ru": name_ru,
        "emoji": emoji,
        "category": category,
        "t_base": t_base,
        "t_upper": t_upper,
        "phases": phases,
    }


CROPS: dict[str, CropDefinition] = {
    "wheat": _crop(
        "Пшеница",
        "🌾",
        "grains",
        5.0,
        ("Всходы", "Кущение", "Выход в трубку", "Колошение", "Молочная спелость", "Полная спелость"),
    ),
    "barley": _crop(
        "Ячмень",
        "🌾",
        "grains",
        5.0,
        ("Всходы", "Кущение", "Выход в трубку", "Колошение", "Полная спелость"),
    ),
    "oat": _crop(
        "Овёс",
        "🌾",
        "grains",
        4.0,
        ("Всходы", "Кущение", "Выход в трубку", "Вымётывание", "Полная спелость"),
    ),
    "rye": _crop(
        "Рожь",
        "🌾",
        "grains",
        5.0,
        ("Всходы", "Кущение", "Выход в трубку", "Колошение", "Полная спелость"),
    ),
    "triticale": _crop(
        "Тритикале",
        "🌾",
        "grains",
        5.0,
        ("Всходы", "Кущение", "Выход в трубку", "Колошение", "Полная спелость"),
    ),
    "sorghum": _crop(
        "Сорго",
        "🌾",
        "grains",
        10.0,
        ("Всходы", "Кущение", "Выход в трубку", "Вымётывание", "Созревание"),
    ),
    "corn": _crop(
        "Кукуруза",
        "🌽",
        "corn_cereals",
        10.0,
        ("Всходы", "6 листьев", "Вымётывание", "Цветение", "Молочная спелость", "Полная спелость"),
    ),
    "millet": _crop(
        "Просо",
        "🌾",
        "corn_cereals",
        10.0,
        ("Всходы", "Кущение", "Выход в трубку", "Вымётывание", "Созревание"),
    ),
    "buckwheat": _crop(
        "Гречиха",
        "🌿",
        "corn_cereals",
        8.0,
        ("Всходы", "Ветвление", "Бутонизация", "Цветение", "Созревание"),
    ),
    "rice": _crop(
        "Рис",
        "🍚",
        "corn_cereals",
        10.0,
        ("Всходы", "Кущение", "Выход в трубку", "Вымётывание", "Созревание"),
    ),
    "sunflower": _crop(
        "Подсолнечник",
        "🌻",
        "oilseeds",
        6.0,
        ("Всходы", "Формирование листьев", "Бутонизация", "Цветение", "Налив семян", "Созревание"),
    ),
    "rapeseed": _crop(
        "Рапс",
        "🌼",
        "oilseeds",
        5.0,
        ("Всходы", "Розетка", "Стеблевание", "Бутонизация", "Цветение", "Созревание"),
    ),
    "flax": _crop(
        "Лён",
        "🌿",
        "oilseeds",
        5.0,
        ("Всходы", "Ёлочка", "Бутонизация", "Цветение", "Созревание"),
    ),
    "soy": _crop(
        "Соя",
        "🫘",
        "oilseeds",
        10.0,
        ("Всходы", "Ветвление", "Бутонизация", "Цветение", "Налив бобов", "Созревание"),
    ),
    "mustard": _crop(
        "Горчица",
        "🌼",
        "oilseeds",
        5.0,
        ("Всходы", "Розетка", "Стеблевание", "Бутонизация", "Цветение", "Созревание"),
    ),
    "potato": _crop(
        "Картофель",
        "🥔",
        "root_crops",
        7.0,
        ("Всходы", "Бутонизация", "Цветение", "Клубнеобразование", "Отмирание ботвы"),
    ),
    "sugarbeet": _crop(
        "Сахарная свёкла",
        "🥕",
        "root_crops",
        5.0,
        ("Всходы", "Первая пара листьев", "Смыкание рядов", "Рост корнеплода", "Техническая спелость"),
    ),
    "carrot": _crop(
        "Морковь",
        "🥕",
        "root_crops",
        5.0,
        ("Всходы", "Формирование розетки", "Рост корнеплода", "Техническая спелость"),
    ),
    "beet": _crop(
        "Свёкла столовая",
        "🟣",
        "root_crops",
        5.0,
        ("Всходы", "Формирование розетки", "Рост корнеплода", "Техническая спелость"),
    ),
    "tomato": _crop(
        "Томат",
        "🍅",
        "vegetables",
        10.0,
        ("Всходы", "Бутонизация", "Цветение", "Завязывание плодов", "Плодоношение"),
    ),
    "cucumber": _crop(
        "Огурец",
        "🥒",
        "vegetables",
        10.0,
        ("Всходы", "Формирование плетей", "Цветение", "Плодоношение"),
    ),
    "zucchini": _crop(
        "Кабачок",
        "🥒",
        "vegetables",
        10.0,
        ("Всходы", "Формирование листьев", "Цветение", "Плодоношение"),
    ),
    "watermelon": _crop(
        "Арбуз",
        "🍉",
        "vegetables",
        10.0,
        ("Всходы", "Формирование плетей", "Цветение", "Рост плодов", "Созревание"),
    ),
    "melon": _crop(
        "Дыня",
        "🍈",
        "vegetables",
        10.0,
        ("Всходы", "Формирование плетей", "Цветение", "Рост плодов", "Созревание"),
    ),
    "onion": _crop(
        "Лук",
        "🧅",
        "vegetables",
        5.0,
        ("Всходы", "Рост листьев", "Формирование луковицы", "Полегание пера"),
    ),
    "garlic": _crop(
        "Чеснок",
        "🧄",
        "vegetables",
        5.0,
        ("Всходы", "Рост листьев", "Формирование луковицы", "Созревание"),
    ),
    "alfalfa": _crop(
        "Люцерна",
        "🌿",
        "forage",
        5.0,
        ("Всходы", "Ветвление", "Бутонизация", "Цветение"),
    ),
    "clover": _crop(
        "Клевер",
        "☘️",
        "forage",
        5.0,
        ("Всходы", "Ветвление", "Бутонизация", "Цветение"),
    ),
    "timothy": _crop(
        "Тимофеевка",
        "🌿",
        "forage",
        5.0,
        ("Всходы", "Кущение", "Выход в трубку", "Вымётывание", "Цветение"),
    ),
    "corn_silage": _crop(
        "Кукуруза на силос",
        "🌽",
        "forage",
        10.0,
        ("Всходы", "6 листьев", "Вымётывание", "Цветение", "Молочная спелость"),
    ),
}


_ALIASES = {
    "soybean": "soy",
    "sugar_beet": "sugarbeet",
}


def normalise_crop_key(crop_key: str) -> str:
    key = _ALIASES.get(crop_key, crop_key)
    if key not in CROPS:
        raise ValueError(f"Неподдерживаемая культура: {crop_key}")
    return key


def get_crop(crop_key: str) -> CropDefinition:
    """Return a supported crop without silently substituting another crop."""
    return CROPS[normalise_crop_key(crop_key)]


def get_crop_name(crop_key: str) -> str:
    return get_crop(crop_key)["name_ru"]


def get_crop_phases(crop_key: str) -> tuple[str, ...]:
    return get_crop(crop_key)["phases"]
