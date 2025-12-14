"""
Модуль для генерации текстовых рекомендаций через OpenRouter LLM
"""
import aiohttp
import os
from config.settings import OPENROUTER_API_KEY


async def generate_crop_recommendation(crop_data, indices, soil_data, user_context=None):
    """
    Генерация текстовой рекомендации с помощью LLM через OpenRouter

    Args:
        crop_data: данные по топ-культурам
        indices: агрономические индексы
        soil_data: данные о почве
        user_context: контекст пользователя (опционально)

    Returns:
        Текстовая рекомендация
    """
    # Формирование промпта
    prompt = build_prompt(crop_data, indices, soil_data, user_context)

    try:
        # Вызов OpenRouter API
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://crop-forecast-bot.com",
                "X-Title": "Crop Forecast Bot",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "anthropic/claude-3.5-sonnet",  # Лучшая модель для анализа
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 1500
            }

            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"Ошибка OpenRouter API: {response.status} - {error_text}")
                    return None

                result = await response.json()
                recommendation_text = result['choices'][0]['message']['content']

                return recommendation_text

    except Exception as e:
        print(f"Ошибка генерации рекомендации: {e}")
        import traceback
        traceback.print_exc()
        return None


def build_prompt(crop_data, indices, soil_data, user_context):
    """
    Построение промпта для LLM

    Args:
        crop_data: список топ-культур
        indices: агрономические индексы
        soil_data: данные о почве
        user_context: контекст пользователя

    Returns:
        Текст промпта
    """
    # Значения по умолчанию для контекста
    if user_context is None:
        user_context = {}

    region = user_context.get('region', 'Россия')
    area_ha = user_context.get('area_ha', 10)
    lat = user_context.get('lat', 0)
    lon = user_context.get('lon', 0)

    # Извлечение данных
    top1 = crop_data[0] if len(crop_data) > 0 else None
    top2 = crop_data[1] if len(crop_data) > 1 else None
    top3 = crop_data[2] if len(crop_data) > 2 else None

    # Климатические условия
    gdd = indices.get('gdd', {})
    gtk = indices.get('gtk', {})
    spi = indices.get('spi', {})
    lai = indices.get('lai', {})

    # Почвенные данные
    texture = soil_data.get('texture', {}) if soil_data else {}
    chemistry = soil_data.get('chemistry', {}) if soil_data else {}
    interpretation = soil_data.get('interpretation', {}) if soil_data else {}

    prompt = f"""
Вы — опытный агроном-консультант для фермеров России.

ДАННЫЕ ФЕРМЫ:
- Регион: {region}
- Площадь: {area_ha} га
- Координаты: {lat:.4f}, {lon:.4f}

КЛИМАТИЧЕСКИЕ УСЛОВИЯ:
- GDD (сумма эффективных температур): {gdd.get('total_gdd', 'н/д')}°C·дни
- ГТК (увлажнение): {gtk.get('gtk', 'н/д')} - {gtk.get('interpretation', 'н/д')}
- SPI (засуха): {spi.get('latest_spi', 'н/д')} - {spi.get('interpretation', 'н/д')}
- LAI (площадь листьев): {lai.get('lai_estimated', 'н/д')} (FPAR: {lai.get('fpar', 0)*100:.0f}%)

ПОЧВА:
- Тип: {texture.get('texture_class_ru', 'н/д')}
- Глина: {texture.get('clay_percent', 'н/д')}%
- Песок: {texture.get('sand_percent', 'н/д')}%
- Гумус: {chemistry.get('soc_percent', 'н/д')*1.724 if chemistry.get('soc_percent') else 'н/д'}%
- pH: {chemistry.get('ph', 'н/д')}
- Плодородность: {interpretation.get('fertility', 'н/д')}
- Рекомендация по почве: {interpretation.get('fertility_recommendation', 'н/д')}

РЕКОМЕНДУЕМЫЕ КУЛЬТУРЫ:

1. **{top1['crop_name_ru'] if top1 else 'н/д'}** (пригодность {top1['suitability_score'] if top1 else 0}%)
   - Оценка: {top1['interpretation'] if top1 else 'н/д'}
   - Детали: {format_details(top1['details']) if top1 else 'н/д'}

2. **{top2['crop_name_ru'] if top2 else 'н/д'}** (пригодность {top2['suitability_score'] if top2 else 0}%)
   - Оценка: {top2['interpretation'] if top2 else 'н/д'}

3. **{top3['crop_name_ru'] if top3 else 'н/д'}** (пригодность {top3['suitability_score'] if top3 else 0}%)
   - Оценка: {top3['interpretation'] if top3 else 'н/д'}

ЗАДАЧА:
Составьте краткие практические рекомендации для фермера (4-5 абзацев):

1. **Выбор культуры**: Какую из трех культур лучше выбрать и почему? Учтите климат, почву и агрономические индексы.

2. **Риски**: Какие основные риски нужно учесть (засуха, заморозки, переувлажнение, кислотность почвы)?

3. **Агротехника**: Практические советы по срокам посева, обработке почвы, удобрениям.

4. **Прогноз**: Примерная ожидаемая урожайность (ц/га) для выбранной культуры в данных условиях.

ВАЖНО:
- Пишите простым языком без профессионального жаргона
- Будьте конкретны и практичны
- Учитывайте все предоставленные данные
- НЕ используйте эмодзи (они будут добавлены автоматически)
"""

    return prompt


def format_details(details):
    """Форматирование деталей для промпта"""
    if not details:
        return ""

    items = []
    for key, value in details.items():
        items.append(f"{key}: {value}")

    return "; ".join(items[:3])  # Первые 3 детали


async def generate_short_summary(crop_name, suitability_score):
    """
    Генерация краткой сводки по культуре

    Args:
        crop_name: название культуры
        suitability_score: оценка пригодности

    Returns:
        Краткое описание (1-2 предложения)
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://crop-forecast-bot.com",
                "X-Title": "Crop Forecast Bot",
                "Content-Type": "application/json"
            }

            prompt = f"""
Напишите одно предложение (до 150 символов) о том, подходит ли культура "{crop_name}"
для выращивания, если оценка пригодности {suitability_score}%.

Будьте кратки и конкретны.
"""

            payload = {
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.5,
                "max_tokens": 100
            }

            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result['choices'][0]['message']['content']

    except Exception as e:
        print(f"Ошибка генерации сводки: {e}")

    return None


def generate_fallback_recommendation(crop_data, indices):
    """
    Генерация простой рекомендации без LLM (fallback)

    Используется если OpenRouter недоступен

    Args:
        crop_data: данные по культурам
        indices: агрономические индексы

    Returns:
        Текстовая рекомендация
    """
    if not crop_data or len(crop_data) == 0:
        return "К сожалению, не удалось подобрать подходящие культуры для ваших условий."

    top1 = crop_data[0]

    lines = []

    lines.append(f"**Рекомендация по выбору культуры**\n")

    lines.append(f"На основе анализа климатических и почвенных условий вашего участка, "
                 f"наиболее подходящей культурой является **{top1['crop_name_ru']}** "
                 f"с оценкой пригодности {top1['suitability_score']:.0f}%.\n")

    # GDD
    if indices.get('gdd'):
        gdd = indices['gdd']
        lines.append(f"Сумма эффективных температур (GDD) составляет {gdd.get('total_gdd', 0):.0f}°C·дни, "
                     f"что должно обеспечить нормальное развитие культуры.")

    # ГТК
    if indices.get('gtk'):
        gtk = indices['gtk']
        lines.append(f"Условия увлажнения: {gtk.get('interpretation', 'нормальные')} "
                     f"(ГТК = {gtk.get('gtk', 1.0)}).")

    # SPI
    if indices.get('spi') and indices['spi'].get('latest_spi') is not None:
        spi = indices['spi']
        spi_val = spi.get('latest_spi')

        if spi_val < -1.0:
            lines.append(f"⚠️ Обратите внимание: текущий индекс засухи (SPI) показывает {spi.get('interpretation')}. "
                         f"Рекомендуется предусмотреть дополнительное орошение.")
        elif spi_val > 1.5:
            lines.append(f"Индекс увлажнения показывает повышенное количество осадков. "
                         f"Убедитесь в хорошем дренаже.")

    lines.append(f"\nДля повышения урожайности рекомендуется:")
    lines.append(f"- Провести анализ почвы для определения потребности в удобрениях")
    lines.append(f"- Соблюдать оптимальные сроки посева")
    lines.append(f"- Обеспечить защиту от вредителей и болезней")

    return "\n".join(lines)
