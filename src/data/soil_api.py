"""
Модуль для работы с почвенными данными SoilGrids
Получает характеристики почвы через REST API
"""
import aiohttp
import asyncio
import numpy as np


async def fetch_soilgrids_data(lat, lon):
    """
    Получение почвенных параметров из SoilGrids REST API

    Параметры:
    - Текстура (clay, sand, silt)
    - Органический углерод (SOC)
    - Азот (nitrogen)
    - pH
    - Bulk density (плотность)

    Args:
        lat: широта
        lon: долгота

    Returns:
        Словарь с характеристиками почвы
    """
    base_url = "https://rest.isric.org/soilgrids/v2.0/properties/query"

    params = {
        'lon': lon,
        'lat': lat,
        'property': ['clay', 'sand', 'silt', 'soc', 'nitrogen', 'phh2o', 'bdod'],
        'depth': ['0-5cm', '5-15cm', '15-30cm', '30-60cm', '60-100cm', '100-200cm'],
        'value': 'mean'
    }

    try:
        async with aiohttp.ClientSession() as session:
            # Формирование запроса
            property_list = ','.join(params['property'])
            depth_list = ','.join(params['depth'])

            url = f"{base_url}?lon={lon}&lat={lat}&property={property_list}&depth={depth_list}&value=mean"

            print(f"Запрос почвенных данных для координат {lat}, {lon}...")

            async with session.get(url) as response:
                if response.status != 200:
                    print(f"Ошибка запроса SoilGrids: HTTP {response.status}")
                    return None

                data = await response.json()

                # Обработка данных
                soil_profile = process_soilgrids_response(data)

                return soil_profile

    except Exception as e:
        print(f"Ошибка при получении данных SoilGrids: {e}")
        import traceback
        traceback.print_exc()
        return None


def process_soilgrids_response(data):
    """
    Обработка ответа от SoilGrids API

    Args:
        data: JSON ответ от API

    Returns:
        Словарь с агрегированными почвенными характеристиками
    """
    try:
        properties = data.get('properties', {}).get('layers', [])

        # Словарь для хранения результатов
        soil_params = {}

        # Обработка каждого параметра
        for prop in properties:
            prop_name = prop.get('name')
            depths = prop.get('depths', [])

            values_by_depth = []

            for depth in depths:
                depth_label = depth.get('label')
                value = depth.get('values', {}).get('mean')

                if value is not None:
                    values_by_depth.append({
                        'depth': depth_label,
                        'value': value
                    })

            # Сохранение по слоям
            soil_params[prop_name] = values_by_depth

        # Расчет средних значений для корнеобитаемого слоя 0-100 см
        clay_0_100 = calculate_weighted_mean(soil_params.get('clay', []), max_depth='100-200cm')
        sand_0_100 = calculate_weighted_mean(soil_params.get('sand', []), max_depth='100-200cm')
        silt_0_100 = calculate_weighted_mean(soil_params.get('silt', []), max_depth='100-200cm')
        soc_0_100 = calculate_weighted_mean(soil_params.get('soc', []), max_depth='100-200cm')
        nitrogen_0_100 = calculate_weighted_mean(soil_params.get('nitrogen', []), max_depth='100-200cm')
        ph_0_100 = calculate_weighted_mean(soil_params.get('phh2o', []), max_depth='100-200cm')
        bdod_0_100 = calculate_weighted_mean(soil_params.get('bdod', []), max_depth='100-200cm')

        # Конвертация единиц
        # Clay, sand, silt: g/kg → %
        clay_pct = clay_0_100 / 10 if clay_0_100 else None
        sand_pct = sand_0_100 / 10 if sand_0_100 else None
        silt_pct = silt_0_100 / 10 if silt_0_100 else None

        # SOC: dg/kg → %
        soc_pct = soc_0_100 / 10 if soc_0_100 else None

        # Nitrogen: cg/kg → %
        nitrogen_pct = nitrogen_0_100 / 100 if nitrogen_0_100 else None

        # pH: pH×10 → pH
        ph = ph_0_100 / 10 if ph_0_100 else None

        # Bulk density: cg/cm³ → g/cm³
        bulk_density = bdod_0_100 / 100 if bdod_0_100 else None

        # Классификация текстуры
        texture_class = classify_texture(clay_pct, sand_pct, silt_pct)

        # Формирование результата
        result = {
            'texture': {
                'clay_percent': round(clay_pct, 2) if clay_pct else None,
                'sand_percent': round(sand_pct, 2) if sand_pct else None,
                'silt_percent': round(silt_pct, 2) if silt_pct else None,
                'texture_class': texture_class,
                'texture_class_ru': get_texture_name_ru(texture_class)
            },
            'chemistry': {
                'soc_percent': round(soc_pct, 2) if soc_pct else None,
                'nitrogen_percent': round(nitrogen_pct, 3) if nitrogen_pct else None,
                'ph': round(ph, 1) if ph else None,
                'c_n_ratio': round(soc_pct / nitrogen_pct, 1) if soc_pct and nitrogen_pct else None
            },
            'physical': {
                'bulk_density': round(bulk_density, 2) if bulk_density else None
            },
            'interpretation': interpret_soil_properties(ph, soc_pct, texture_class),
            'raw_data': soil_params
        }

        return result

    except Exception as e:
        print(f"Ошибка обработки данных SoilGrids: {e}")
        import traceback
        traceback.print_exc()
        return None


def calculate_weighted_mean(values_list, max_depth='100-200cm'):
    """
    Расчет взвешенного среднего по глубинам почвы

    Args:
        values_list: список значений по глубинам
        max_depth: максимальная глубина для учета

    Returns:
        Взвешенное среднее значение
    """
    if not values_list:
        return None

    # Веса для разных глубин (в см)
    depth_weights = {
        '0-5cm': 5,
        '5-15cm': 10,
        '15-30cm': 15,
        '30-60cm': 30,
        '60-100cm': 40,
        '100-200cm': 0  # Не учитываем по умолчанию
    }

    total_weight = 0
    weighted_sum = 0

    for item in values_list:
        depth = item['depth']
        value = item['value']

        if depth in depth_weights and value is not None:
            weight = depth_weights[depth]
            weighted_sum += value * weight
            total_weight += weight

    if total_weight == 0:
        return None

    return weighted_sum / total_weight


def classify_texture(clay, sand, silt):
    """
    Классификация механического состава почвы по USDA

    Args:
        clay: содержание глины (%)
        sand: содержание песка (%)
        silt: содержание ила (%)

    Returns:
        Класс текстуры
    """
    if clay is None or sand is None or silt is None:
        return 'unknown'

    # Упрощенная классификация USDA
    if clay >= 40:
        return 'heavy_clay'
    elif clay >= 35:
        return 'clay'
    elif clay >= 27:
        if sand >= 45:
            return 'sandy_clay_loam'
        else:
            return 'clay_loam'
    elif sand >= 85:
        return 'sand'
    elif sand >= 70:
        if silt >= 15:
            return 'sandy_loam'
        else:
            return 'loamy_sand'
    elif sand >= 52:
        return 'sandy_loam'
    elif silt >= 50:
        if clay >= 18:
            return 'silty_clay_loam'
        else:
            return 'silt_loam'
    elif silt >= 80:
        return 'silt'
    else:
        return 'loam'


def get_texture_name_ru(texture_class):
    """Получение русского названия текстуры"""
    names = {
        'sand': 'Песок',
        'loamy_sand': 'Супесь',
        'sandy_loam': 'Легкий суглинок',
        'sandy_clay_loam': 'Суглинок',
        'loam': 'Средний суглинок',
        'silt_loam': 'Пылеватый суглинок',
        'silt': 'Пыль',
        'clay_loam': 'Тяжелый суглинок',
        'silty_clay_loam': 'Пылевато-глинистый суглинок',
        'clay': 'Глина',
        'heavy_clay': 'Тяжелая глина',
        'unknown': 'Неопределено'
    }
    return names.get(texture_class, texture_class)


def interpret_soil_properties(ph, soc, texture_class):
    """
    Интерпретация почвенных характеристик для агрономии

    Args:
        ph: кислотность почвы
        soc: содержание органического углерода (%)
        texture_class: класс текстуры

    Returns:
        Словарь с интерпретацией
    """
    interpretation = {}

    # Оценка pH
    if ph is not None:
        if ph < 5.5:
            interpretation['ph_level'] = 'сильнокислая'
            interpretation['ph_recommendation'] = 'Требуется известкование'
        elif ph < 6.5:
            interpretation['ph_level'] = 'слабокислая'
            interpretation['ph_recommendation'] = 'Подходит для большинства культур'
        elif ph < 7.5:
            interpretation['ph_level'] = 'нейтральная'
            interpretation['ph_recommendation'] = 'Оптимально'
        elif ph < 8.5:
            interpretation['ph_level'] = 'слабощелочная'
            interpretation['ph_recommendation'] = 'Возможны проблемы с усвоением микроэлементов'
        else:
            interpretation['ph_level'] = 'сильнощелочная'
            interpretation['ph_recommendation'] = 'Требуется гипсование'

    # Оценка гумуса (органического вещества)
    if soc is not None:
        # Конвертация SOC в гумус (примерно ×1.724)
        humus = soc * 1.724
        if humus < 2:
            interpretation['fertility'] = 'низкая'
            interpretation['fertility_recommendation'] = 'Необходимо внесение органических удобрений'
        elif humus < 4:
            interpretation['fertility'] = 'средняя'
            interpretation['fertility_recommendation'] = 'Поддерживающее внесение органики'
        elif humus < 6:
            interpretation['fertility'] = 'повышенная'
            interpretation['fertility_recommendation'] = 'Хорошая плодородность'
        else:
            interpretation['fertility'] = 'высокая'
            interpretation['fertility_recommendation'] = 'Отличная плодородность'

    # Оценка текстуры
    texture_suitability = {
        'sand': 'Легкая, требует частых поливов и подкормок',
        'loamy_sand': 'Довольно легкая, хорошая аэрация',
        'sandy_loam': 'Хорошая для большинства культур',
        'loam': 'Оптимальная для земледелия',
        'silt_loam': 'Хорошая влагоемкость',
        'clay_loam': 'Хорошая, но может быть тяжелой в обработке',
        'clay': 'Тяжелая, высокая влагоемкость',
        'heavy_clay': 'Очень тяжелая, требует улучшения структуры'
    }

    interpretation['texture_note'] = texture_suitability.get(texture_class, 'Информация недоступна')

    return interpretation


async def get_soil_nutrients_estimate(lat, lon, texture_data):
    """
    Оценка потенциальных запасов NPK на основе почвенных данных

    Примерная оценка на основе текстуры и органики

    Args:
        lat: широта
        lon: долгота
        texture_data: данные о текстуре и органике

    Returns:
        Словарь с оценкой NPK
    """
    soc_pct = texture_data.get('chemistry', {}).get('soc_percent')
    texture_class = texture_data.get('texture', {}).get('texture_class')

    if not soc_pct or not texture_class:
        return None

    # Примерные коэффициенты для расчета NPK (упрощенная модель)
    # В реальности нужны лабораторные анализы

    # Азот (примерно 5% от органического вещества)
    humus_pct = soc_pct * 1.724
    total_n_pct = humus_pct * 0.05

    # Фосфор и калий зависят от типа почвы и родительской породы
    # Это очень грубая оценка
    texture_npk_factors = {
        'sand': {'P': 0.02, 'K': 0.5},
        'loamy_sand': {'P': 0.03, 'K': 0.8},
        'sandy_loam': {'P': 0.05, 'K': 1.0},
        'loam': {'P': 0.08, 'K': 1.5},
        'silt_loam': {'P': 0.07, 'K': 1.3},
        'clay_loam': {'P': 0.10, 'K': 2.0},
        'clay': {'P': 0.12, 'K': 2.5},
        'heavy_clay': {'P': 0.15, 'K': 3.0}
    }

    factors = texture_npk_factors.get(texture_class, {'P': 0.05, 'K': 1.0})

    return {
        'total_nitrogen_percent': round(total_n_pct, 3),
        'available_p2o5_mg_per_kg': round(factors['P'] * 1000, 1),
        'available_k2o_mg_per_kg': round(factors['K'] * 100, 1),
        'note': 'Это примерная оценка. Для точных данных требуется лабораторный анализ почвы.'
    }
