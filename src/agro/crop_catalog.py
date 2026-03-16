"""
Каталог сельскохозяйственных культур.

Единый источник истины для:
  - клавиатур выбора культуры (keyboards.py)
  - агроиндексов (indices.py)
  - будущего ML-модуля

Структура:
  CATEGORIES — dict[cat_id, {label, emoji, crops: list[crop_key]}]
  CROPS       — dict[crop_key, {name_ru, emoji, t_base, gdd_stages, category}]
"""

# ─────────────────────────────────────────────────────────────
# Категории культур
# ─────────────────────────────────────────────────────────────
CATEGORIES: dict = {
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
        "crops": ["tomato", "cucumber", "zucchini", "watermelon", "melon", "onion", "garlic"],
    },
    "forage": {
        "label": "Кормовые",
        "emoji": "🌿",
        "crops": ["alfalfa", "clover", "timothy", "corn_silage"],
    },
}

# ─────────────────────────────────────────────────────────────
# Культуры
# t_base  — базовая температура для расчёта ГДД (°C)
# gdd_stages — {phase_name: накопленные ГДД от посева}
# ─────────────────────────────────────────────────────────────
CROPS: dict = {
    # ── Зерновые ────────────────────────────────────────────
    "wheat": {
        "name_ru": "Пшеница",
        "emoji": "🌾",
        "t_base": 5.0,
        "category": "grains",
        "gdd_stages": {
            "Всходы":         100,
            "Кущение":        300,
            "Выход в трубку": 600,
            "Колошение":      900,
            "Молочная спелость": 1200,
            "Полная спелость":   1500,
        },
    },
    "barley": {
        "name_ru": "Ячмень",
        "emoji": "🌾",
        "t_base": 5.0,
        "category": "grains",
        "gdd_stages": {
            "Всходы":         90,
            "Кущение":        250,
            "Выход в трубку": 550,
            "Колошение":      800,
            "Полная спелость":  1300,
        },
    },
    "oat": {
        "name_ru": "Овёс",
        "emoji": "🌾",
        "t_base": 4.0,
        "category": "grains",
        "gdd_stages": {
            "Всходы":       100,
            "Кущение":      300,
            "Выметывание":  700,
            "Полная спелость": 1400,
        },
    },
    "rye": {
        "name_ru": "Рожь",
        "emoji": "🌾",
        "t_base": 5.0,
        "category": "grains",
        "gdd_stages": {
            "Всходы":       90,
            "Кущение":      280,
            "Колошение":    850,
            "Полная спелость": 1450,
        },
    },
    "triticale": {
        "name_ru": "Тритикале",
        "emoji": "🌾",
        "t_base": 5.0,
        "category": "grains",
        "gdd_stages": {
            "Всходы":       95,
            "Кущение":      290,
            "Колошение":    870,
            "Полная спелость": 1480,
        },
    },
    "sorghum": {
        "name_ru": "Сорго",
        "emoji": "🌾",
        "t_base": 10.0,
        "category": "grains",
        "gdd_stages": {
            "Всходы":       165,
            "Выметывание":  800,
            "Полная спелость": 1400,
        },
    },
    # ── Кукуруза / крупы ────────────────────────────────────
    "corn": {
        "name_ru": "Кукуруза",
        "emoji": "🌽",
        "t_base": 10.0,
        "category": "corn_cereals",
        "gdd_stages": {
            "Всходы":        100,
            "6 листьев":     380,
            "Выметывание":   800,
            "Молочная спелость": 1100,
            "Полная спелость":   1400,
        },
    },
    "millet": {
        "name_ru": "Просо",
        "emoji": "🌾",
        "t_base": 10.0,
        "category": "corn_cereals",
        "gdd_stages": {
            "Всходы":       150,
            "Выметывание":  700,
            "Полная спелость": 1200,
        },
    },
    "buckwheat": {
        "name_ru": "Гречиха",
        "emoji": "🌿",
        "t_base": 8.0,
        "category": "corn_cereals",
        "gdd_stages": {
            "Всходы":       100,
            "Цветение":     500,
            "Полная спелость": 900,
        },
    },
    "rice": {
        "name_ru": "Рис",
        "emoji": "🍚",
        "t_base": 10.0,
        "category": "corn_cereals",
        "gdd_stages": {
            "Всходы":       150,
            "Выметывание":  900,
            "Полная спелость": 1500,
        },
    },
    # ── Масличные ───────────────────────────────────────────
    "sunflower": {
        "name_ru": "Подсолнечник",
        "emoji": "🌻",
        "t_base": 6.0,
        "category": "oilseeds",
        "gdd_stages": {
            "Всходы":       170,
            "Бутонизация":  600,
            "Цветение":     850,
            "Полная спелость": 1400,
        },
    },
    "rapeseed": {
        "name_ru": "Рапс",
        "emoji": "🌼",
        "t_base": 5.0,
        "category": "oilseeds",
        "gdd_stages": {
            "Всходы":       100,
            "Цветение":     600,
            "Полная спелость": 1300,
        },
    },
    "flax": {
        "name_ru": "Лён",
        "emoji": "🌿",
        "t_base": 5.0,
        "category": "oilseeds",
        "gdd_stages": {
            "Всходы":       100,
            "Цветение":     500,
            "Полная спелость": 950,
        },
    },
    "soy": {
        "name_ru": "Соя",
        "emoji": "🫘",
        "t_base": 10.0,
        "category": "oilseeds",
        "gdd_stages": {
            "Всходы":       100,
            "Цветение":     500,
            "Налив бобов":  900,
            "Полная спелость": 1300,
        },
    },
    "mustard": {
        "name_ru": "Горчица",
        "emoji": "🌼",
        "t_base": 5.0,
        "category": "oilseeds",
        "gdd_stages": {
            "Всходы":       80,
            "Цветение":     400,
            "Полная спелость": 800,
        },
    },
    # ── Корнеплоды ──────────────────────────────────────────
    "potato": {
        "name_ru": "Картофель",
        "emoji": "🥔",
        "t_base": 7.0,
        "category": "root_crops",
        "gdd_stages": {
            "Всходы":       200,
            "Бутонизация":  600,
            "Полная спелость": 1200,
        },
    },
    "sugarbeet": {
        "name_ru": "Сахарная свёкла",
        "emoji": "🥕",
        "t_base": 5.0,
        "category": "root_crops",
        "gdd_stages": {
            "Всходы":       150,
            "Смыкание рядов": 600,
            "Техническая спелость": 1400,
        },
    },
    "carrot": {
        "name_ru": "Морковь",
        "emoji": "🥕",
        "t_base": 5.0,
        "category": "root_crops",
        "gdd_stages": {
            "Всходы":       120,
            "Техническая спелость": 900,
        },
    },
    "beet": {
        "name_ru": "Свёкла столовая",
        "emoji": "🟣",
        "t_base": 5.0,
        "category": "root_crops",
        "gdd_stages": {
            "Всходы":       120,
            "Техническая спелость": 850,
        },
    },
    # ── Овощи / бахчевые ────────────────────────────────────
    "tomato": {
        "name_ru": "Томат",
        "emoji": "🍅",
        "t_base": 10.0,
        "category": "vegetables",
        "gdd_stages": {
            "Всходы":       150,
            "Цветение":     450,
            "Плодоношение": 900,
        },
    },
    "cucumber": {
        "name_ru": "Огурец",
        "emoji": "🥒",
        "t_base": 10.0,
        "category": "vegetables",
        "gdd_stages": {
            "Всходы":       100,
            "Цветение":     300,
            "Плодоношение": 700,
        },
    },
    "zucchini": {
        "name_ru": "Кабачок",
        "emoji": "🥒",
        "t_base": 10.0,
        "category": "vegetables",
        "gdd_stages": {
            "Всходы":       100,
            "Плодоношение": 650,
        },
    },
    "watermelon": {
        "name_ru": "Арбуз",
        "emoji": "🍉",
        "t_base": 10.0,
        "category": "vegetables",
        "gdd_stages": {
            "Всходы":       150,
            "Цветение":     500,
            "Полная спелость": 1200,
        },
    },
    "melon": {
        "name_ru": "Дыня",
        "emoji": "🍈",
        "t_base": 10.0,
        "category": "vegetables",
        "gdd_stages": {
            "Всходы":       150,
            "Цветение":     500,
            "Полная спелость": 1100,
        },
    },
    "onion": {
        "name_ru": "Лук",
        "emoji": "🧅",
        "t_base": 5.0,
        "category": "vegetables",
        "gdd_stages": {
            "Всходы":       150,
            "Луковица":     700,
        },
    },
    "garlic": {
        "name_ru": "Чеснок",
        "emoji": "🧄",
        "t_base": 5.0,
        "category": "vegetables",
        "gdd_stages": {
            "Всходы":       120,
            "Полная спелость": 800,
        },
    },
    # ── Кормовые ────────────────────────────────────────────
    "alfalfa": {
        "name_ru": "Люцерна",
        "emoji": "🌿",
        "t_base": 5.0,
        "category": "forage",
        "gdd_stages": {
            "Всходы":   100,
            "Цветение": 600,
        },
    },
    "clover": {
        "name_ru": "Клевер",
        "emoji": "☘️",
        "t_base": 5.0,
        "category": "forage",
        "gdd_stages": {
            "Всходы":   100,
            "Цветение": 550,
        },
    },
    "timothy": {
        "name_ru": "Тимофеевка",
        "emoji": "🌿",
        "t_base": 5.0,
        "category": "forage",
        "gdd_stages": {
            "Всходы":   90,
            "Выметывание": 500,
        },
    },
    "corn_silage": {
        "name_ru": "Кукуруза на силос",
        "emoji": "🌽",
        "t_base": 10.0,
        "category": "forage",
        "gdd_stages": {
            "Всходы":       100,
            "6 листьев":    380,
            "Молочная спелость": 1000,
        },
    },
}


def get_crop(crop_key: str) -> dict:
    """Возвращает данные культуры по ключу, или wheat по умолчанию."""
    return CROPS.get(crop_key, CROPS["wheat"])


def get_crop_name(crop_key: str) -> str:
    """Возвращает русское название культуры."""
    return CROPS.get(crop_key, CROPS["wheat"])["name_ru"]
