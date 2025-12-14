"""
Обработчик для получения рекомендаций по культурам
Интегрирует все модули: климат, почву, индексы, модели
"""
import asyncio
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim

# Импорт модулей данных
from src.data.climate_api import fetch_era5_extended_data
from src.data.satellite_api import get_satellite_summary
from src.data.soil_api import fetch_soilgrids_data

# Импорт моделей
from src.models.indices import calculate_all_indices, get_indices_summary
from src.models.crop_suitability import (
    get_top_n_crops,
    prepare_region_features,
    format_suitability_report
)
from src.models.economics import (
    estimate_yield,
    calculate_profitability,
    assess_climate_risks,
    calculate_final_rating,
    format_economics_report
)
from src.models.llm_recommender import (
    generate_crop_recommendation,
    generate_fallback_recommendation
)


geolocator = Nominatim(user_agent="crop_recommendation_bot")


async def handle_crop_recommendation_request(bot, message):
    """
    Главный обработчик запроса на рекомендации по культурам

    Args:
        bot: экземпляр бота
        message: сообщение от пользователя с координатами
    """
    lat = message.location.latitude
    lon = message.location.longitude
    user_id = message.from_user.id

    try:
        # Получение адреса
        location = geolocator.reverse((lat, lon), language='ru')
        address = location.address if location else "Адрес не определен"

        # Отправка приветственного сообщения
        await bot.send_message(
            message.chat.id,
            f"🌍 Анализирую условия для вашего участка...\n"
            f"📍 {address}\n\n"
            f"Это займет 2-3 минуты. Пожалуйста, подождите."
        )

        # Шаг 1: Климатические данные
        status_msg = await bot.send_message(
            message.chat.id,
            "☁️ 1/6 Загружаю климатические данные ERA5..."
        )

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)  # Последний год

        climate_data = await fetch_era5_extended_data(
            lat, lon,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )

        if not climate_data:
            await bot.edit_message_text(
                "❌ Не удалось получить климатические данные. Попробуйте позже.",
                message.chat.id,
                status_msg.message_id
            )
            return

        # Шаг 2: Спутниковые данные (NDVI, LAI)
        await bot.edit_message_text(
            "🛰️ 2/6 Получаю спутниковые данные (NDVI, LAI)...",
            message.chat.id,
            status_msg.message_id
        )

        try:
            # Используем последние 6 месяцев для NDVI
            sat_start = end_date - timedelta(days=180)
            satellite_data = await get_satellite_summary(
                lat, lon,
                sat_start.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            )
        except Exception as e:
            print(f"Ошибка получения спутниковых данных: {e}")
            satellite_data = None

        # Шаг 3: Почвенные данные
        await bot.edit_message_text(
            "🌱 3/6 Анализирую почву...",
            message.chat.id,
            status_msg.message_id
        )

        soil_data = await fetch_soilgrids_data(lat, lon)

        # Шаг 4: Расчет агрономических индексов
        await bot.edit_message_text(
            "📊 4/6 Рассчитываю агрономические индексы (GDD, SPI, ГТК, LAI)...",
            message.chat.id,
            status_msg.message_id
        )

        # Подготовка данных для расчета индексов
        ndvi_timeseries = None
        if satellite_data and satellite_data.get('ndvi_timeseries'):
            ndvi_timeseries = satellite_data['ndvi_timeseries']

        indices = calculate_all_indices(climate_data, ndvi_timeseries)

        # Шаг 5: Подбор культур
        await bot.edit_message_text(
            "🌾 5/6 Подбираю оптимальные культуры...",
            message.chat.id,
            status_msg.message_id
        )

        # Подготовка данных региона
        region_data = prepare_region_features(climate_data, soil_data, indices)

        # Получение топ-3 культур
        top3_crops = get_top_n_crops(region_data, n=3)

        # Расчет урожайности, экономики и рисков для каждой культуры
        for crop in top3_crops:
            crop_name = crop['crop']

            # Прогноз урожайности
            yield_forecast = estimate_yield(
                crop_name,
                crop['suitability_score'],
                indices
            )
            crop['yield_forecast'] = yield_forecast

            # Экономика
            if yield_forecast:
                profitability = calculate_profitability(crop_name, yield_forecast)
                crop['economics'] = profitability
            else:
                crop['economics'] = None

            # Риски
            risk_assessment = assess_climate_risks(climate_data, indices, crop_name)
            crop['risks'] = risk_assessment

            # Финальный рейтинг
            if crop['economics']:
                final_rating = calculate_final_rating(
                    crop['suitability_score'],
                    crop['economics'],
                    risk_assessment
                )
                crop['final_rating'] = final_rating
            else:
                crop['final_rating'] = crop['suitability_score']

        # Сортировка по финальному рейтингу
        top3_crops.sort(key=lambda x: x['final_rating'], reverse=True)

        # Шаг 6: Генерация LLM рекомендации
        await bot.edit_message_text(
            "✍️ 6/6 Формирую персональные рекомендации...",
            message.chat.id,
            status_msg.message_id
        )

        user_context = {
            'region': address.split(',')[0] if address else 'Россия',
            'area_ha': 10,  # По умолчанию
            'lat': lat,
            'lon': lon
        }

        # Попытка получить LLM рекомендацию
        llm_recommendation = await generate_crop_recommendation(
            top3_crops,
            indices,
            soil_data,
            user_context
        )

        # Fallback если LLM недоступен
        if not llm_recommendation:
            llm_recommendation = generate_fallback_recommendation(top3_crops, indices)

        # Удаление статусного сообщения
        await bot.delete_message(message.chat.id, status_msg.message_id)

        # Формирование финального отчета
        report = format_final_report(
            top3_crops,
            indices,
            soil_data,
            llm_recommendation,
            address
        )

        # Отправка отчета
        await bot.send_message(
            message.chat.id,
            report,
            parse_mode='Markdown'
        )

        # Отправка детальной экономики для топ-1
        if top3_crops[0].get('economics') and top3_crops[0].get('risks'):
            economics_report = format_economics_report(
                top3_crops[0]['crop'],
                top3_crops[0]['economics'],
                top3_crops[0]['risks']
            )

            await bot.send_message(
                message.chat.id,
                f"```\n{economics_report}\n```",
                parse_mode='Markdown'
            )

    except Exception as e:
        print(f"Ошибка в обработчике рекомендаций: {e}")
        import traceback
        traceback.print_exc()

        await bot.send_message(
            message.chat.id,
            f"❌ Произошла ошибка при обработке запроса:\n{str(e)}\n\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку."
        )


def format_final_report(top3_crops, indices, soil_data, llm_text, address):
    """
    Форматирование финального отчета для пользователя

    Args:
        top3_crops: топ-3 культуры
        indices: агрономические индексы
        soil_data: данные о почве
        llm_text: текст рекомендации от LLM
        address: адрес участка

    Returns:
        Форматированный отчет
    """
    lines = []

    # Заголовок
    lines.append("🌾 **РЕКОМЕНДАЦИИ ДЛЯ ВАШЕЙ ФЕРМЫ**\n")
    lines.append(f"📍 **Местоположение:** {address}\n")

    # Климатические условия
    lines.append("📊 **КЛИМАТИЧЕСКИЕ УСЛОВИЯ:**")

    if indices.get('gdd'):
        gdd = indices['gdd']
        lines.append(f"- GDD: {gdd['total_gdd']:.0f}°C·дни")

    if indices.get('gtk'):
        gtk = indices['gtk']
        lines.append(f"- ГТК: {gtk['gtk']} ({gtk['interpretation']})")

    if indices.get('spi') and indices['spi'].get('latest_spi') is not None:
        spi = indices['spi']
        lines.append(f"- SPI: {spi['latest_spi']:.2f} ({spi['interpretation']})")

    if indices.get('lai') and indices['lai'].get('lai_estimated'):
        lai = indices['lai']
        lines.append(f"- LAI: {lai['lai_estimated']} (FPAR: {lai['fpar']*100:.0f}%)")

    lines.append("")

    # Почва
    if soil_data:
        lines.append("🌱 **ПОЧВА:**")
        texture = soil_data.get('texture', {})
        chemistry = soil_data.get('chemistry', {})

        lines.append(f"- Тип: {texture.get('texture_class_ru', 'н/д')}")
        lines.append(f"- pH: {chemistry.get('ph', 'н/д')}")
        if chemistry.get('soc_percent'):
            humus = chemistry['soc_percent'] * 1.724
            lines.append(f"- Гумус: {humus:.1f}%")

        lines.append("")

    # Топ-3 культуры
    lines.append("🏆 **ТОП-3 КУЛЬТУРЫ:**\n")

    for i, crop in enumerate(top3_crops, 1):
        lines.append(f"**{i}. {crop['crop_name_ru']}** (рейтинг {crop['final_rating']:.0f}/100)")

        if crop.get('yield_forecast'):
            lines.append(f"   📊 Ожидаемая урожайность: {crop['yield_forecast']:.1f} ц/га")

        if crop.get('economics'):
            econ = crop['economics']
            lines.append(f"   💰 Прибыль: {econ['profit']:,.0f} ₽/га")
            lines.append(f"   📈 ROI: {econ['roi_percent']:.1f}%")

        if crop.get('risks'):
            risk = crop['risks']
            lines.append(f"   ⚠️ Риски: {risk['interpretation']}")

        lines.append("")

    # LLM рекомендация
    lines.append("---\n")
    lines.append("💡 **ПЕРСОНАЛЬНЫЕ РЕКОМЕНДАЦИИ:**\n")
    lines.append(llm_text)

    # Подвал
    lines.append("\n---")
    lines.append(f"📅 Отчет создан: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    return "\n".join(lines)
