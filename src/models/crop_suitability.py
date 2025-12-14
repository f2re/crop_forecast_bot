"""
Модуль для расчета пригодности культур
Включает матрицу зависимостей и алгоритм расчета рейтинга
"""
import numpy as np
import pandas as pd


# Матрица параметров культур (15 параметров)
CROP_PARAMETERS = {
    'wheat': {
        # Метеорологические параметры (1-5)
        'T_opt_range': (15, 25),       # Оптимальная температура (°C)
        'T_base': 5,                    # Биологический минимум (°C)
        'precip_min': 400,              # Минимальные осадки (мм/год)
        'precip_opt': 600,              # Оптимальные осадки (мм/год)
        'radiation_min': 4000,          # Минимальная радиация (МДж/м²/сезон)

        # Агрогидрологические параметры (6-9)
        'soil_moisture_min': 0.6,       # Мин. запасы влаги (доля от НВ)
        'gtk_opt_range': (1.0, 1.5),    # Оптимальный ГТК
        'soil_type_pref': ['loam', 'silty_loam', 'clay_loam', 'clay'],
        'frost_tolerance': -18,         # Морозостойкость (°C)

        # Биометрические параметры (10-13)
        'gdd_requirement': 1800,        # Сумма эффективных температур
        'lai_optimal': 5.5,             # Оптимальный LAI
        'plant_density': 450,           # Густота стояния (шт/м²)
        'growth_duration': 240,         # Вегетационный период (дни)

        # Спутниковые индексы (14-15)
        'ndvi_threshold': 0.65,         # Порог NDVI для хорошего состояния
        'spi_tolerance': -1.0,          # Толерантность к засухе (SPI)

        # Мета-информация
        'name_ru': 'Пшеница',
        'category': 'Зерновые'
    },

    'corn': {
        'T_opt_range': (20, 30),
        'T_base': 10,
        'precip_min': 500,
        'precip_opt': 700,
        'radiation_min': 5000,
        'soil_moisture_min': 0.7,
        'gtk_opt_range': (1.2, 1.8),
        'soil_type_pref': ['loam', 'silty_loam', 'sandy_loam'],
        'frost_tolerance': 0,
        'gdd_requirement': 2700,
        'lai_optimal': 6.0,
        'plant_density': 7,
        'growth_duration': 150,
        'ndvi_threshold': 0.75,
        'spi_tolerance': -0.5,
        'name_ru': 'Кукуруза',
        'category': 'Зерновые'
    },

    'sunflower': {
        'T_opt_range': (20, 27),
        'T_base': 8,
        'precip_min': 400,
        'precip_opt': 550,
        'radiation_min': 4500,
        'soil_moisture_min': 0.5,
        'gtk_opt_range': (0.8, 1.3),
        'soil_type_pref': ['loam', 'sandy_loam', 'clay_loam'],
        'frost_tolerance': -5,
        'gdd_requirement': 2100,
        'lai_optimal': 4.5,
        'plant_density': 6,
        'growth_duration': 120,
        'ndvi_threshold': 0.70,
        'spi_tolerance': -1.2,
        'name_ru': 'Подсолнечник',
        'category': 'Масличные'
    },

    'soybean': {
        'T_opt_range': (20, 30),
        'T_base': 10,
        'precip_min': 500,
        'precip_opt': 650,
        'radiation_min': 4800,
        'soil_moisture_min': 0.65,
        'gtk_opt_range': (1.1, 1.6),
        'soil_type_pref': ['loam', 'silty_loam', 'sandy_loam'],
        'frost_tolerance': 0,
        'gdd_requirement': 2500,
        'lai_optimal': 5.0,
        'plant_density': 50,
        'growth_duration': 130,
        'ndvi_threshold': 0.72,
        'spi_tolerance': -0.8,
        'name_ru': 'Соя',
        'category': 'Зернобобовые'
    },

    'barley': {
        'T_opt_range': (15, 22),
        'T_base': 5,
        'precip_min': 350,
        'precip_opt': 550,
        'radiation_min': 3800,
        'soil_moisture_min': 0.55,
        'gtk_opt_range': (0.9, 1.4),
        'soil_type_pref': ['loam', 'sandy_loam', 'silty_loam'],
        'frost_tolerance': -20,
        'gdd_requirement': 1500,
        'lai_optimal': 5.0,
        'plant_density': 400,
        'growth_duration': 90,
        'ndvi_threshold': 0.63,
        'spi_tolerance': -1.3,
        'name_ru': 'Ячмень',
        'category': 'Зерновые'
    },

    'rapeseed': {
        'T_opt_range': (15, 25),
        'T_base': 5,
        'precip_min': 450,
        'precip_opt': 650,
        'radiation_min': 4200,
        'soil_moisture_min': 0.65,
        'gtk_opt_range': (1.1, 1.6),
        'soil_type_pref': ['loam', 'clay_loam', 'silty_loam'],
        'frost_tolerance': -15,
        'gdd_requirement': 2000,
        'lai_optimal': 5.5,
        'plant_density': 80,
        'growth_duration': 300,
        'ndvi_threshold': 0.68,
        'spi_tolerance': -0.9,
        'name_ru': 'Рапс',
        'category': 'Масличные'
    },

    'potato': {
        'T_opt_range': (15, 20),
        'T_base': 7,
        'precip_min': 500,
        'precip_opt': 700,
        'radiation_min': 3500,
        'soil_moisture_min': 0.7,
        'gtk_opt_range': (1.3, 1.8),
        'soil_type_pref': ['sandy_loam', 'loam'],
        'frost_tolerance': -2,
        'gdd_requirement': 1400,
        'lai_optimal': 4.0,
        'plant_density': 5,
        'growth_duration': 120,
        'ndvi_threshold': 0.65,
        'spi_tolerance': -0.7,
        'name_ru': 'Картофель',
        'category': 'Технические'
    },

    'sugar_beet': {
        'T_opt_range': (18, 25),
        'T_base': 10,
        'precip_min': 500,
        'precip_opt': 650,
        'radiation_min': 4500,
        'soil_moisture_min': 0.7,
        'gtk_opt_range': (1.2, 1.7),
        'soil_type_pref': ['loam', 'silty_loam', 'clay_loam'],
        'frost_tolerance': -3,
        'gdd_requirement': 2000,
        'lai_optimal': 5.0,
        'plant_density': 10,
        'growth_duration': 180,
        'ndvi_threshold': 0.70,
        'spi_tolerance': -0.6,
        'name_ru': 'Сахарная свекла',
        'category': 'Технические'
    }
}


def calculate_suitability_score(region_data, crop_name):
    """
    Расчет рейтинга пригодности культуры (0-100%)

    Использует метод взвешенной оценки по 15 параметрам

    Args:
        region_data: словарь с данными региона
        crop_name: название культуры

    Returns:
        Словарь с оценкой пригодности и детализацией
    """
    if crop_name not in CROP_PARAMETERS:
        return None

    crop_params = CROP_PARAMETERS[crop_name]

    # Веса для разных категорий параметров
    weights = {
        'temperature': 0.20,
        'precipitation': 0.20,
        'soil': 0.15,
        'gdd': 0.15,
        'moisture': 0.10,
        'radiation': 0.10,
        'frost': 0.10
    }

    scores = {}
    details = {}

    # 1. Оценка температуры
    if 'temperature_avg' in region_data:
        T_avg = region_data['temperature_avg']
        T_opt_min, T_opt_max = crop_params['T_opt_range']

        if T_opt_min <= T_avg <= T_opt_max:
            scores['temperature'] = 1.0
            details['temperature'] = f"Оптимальная ({T_avg:.1f}°C)"
        else:
            deviation = min(abs(T_avg - T_opt_min), abs(T_avg - T_opt_max))
            scores['temperature'] = max(0, 1 - deviation / 10)
            details['temperature'] = f"Отклонение от оптимума: {deviation:.1f}°C"
    else:
        scores['temperature'] = 0.5
        details['temperature'] = "Нет данных"

    # 2. Оценка осадков
    if 'precipitation_annual' in region_data or 'precipitation_sum' in region_data:
        P = region_data.get('precipitation_annual', region_data.get('precipitation_sum', 0))
        P_opt = crop_params['precip_opt']
        P_min = crop_params['precip_min']

        if P >= P_min:
            # Гауссова функция с пиком в P_opt
            scores['precipitation'] = np.exp(-((P - P_opt) / (0.3 * P_opt))**2)
            if P < P_min:
                details['precipitation'] = f"Недостаточно ({P:.0f} < {P_min} мм)"
            else:
                details['precipitation'] = f"Подходит ({P:.0f} мм)"
        else:
            scores['precipitation'] = P / P_min * 0.5
            details['precipitation'] = f"Очень мало ({P:.0f} мм)"
    else:
        scores['precipitation'] = 0.5
        details['precipitation'] = "Нет данных"

    # 3. Оценка почвы
    if 'soil_type' in region_data:
        soil_type = region_data['soil_type']
        if soil_type in crop_params['soil_type_pref']:
            scores['soil'] = 1.0
            details['soil'] = f"Подходящий тип ({soil_type})"
        else:
            scores['soil'] = 0.5
            details['soil'] = f"Не оптимальный тип ({soil_type})"
    else:
        scores['soil'] = 0.5
        details['soil'] = "Нет данных"

    # 4. Оценка GDD
    if 'gdd' in region_data:
        gdd_actual = region_data['gdd']
        gdd_required = crop_params['gdd_requirement']

        if gdd_actual >= gdd_required:
            scores['gdd'] = 1.0
            details['gdd'] = f"Достаточно ({gdd_actual:.0f} >= {gdd_required})"
        else:
            scores['gdd'] = gdd_actual / gdd_required
            details['gdd'] = f"Недостаточно ({gdd_actual:.0f} / {gdd_required})"
    else:
        scores['gdd'] = 0.5
        details['gdd'] = "Нет данных"

    # 5. Оценка влаги в почве
    if 'soil_moisture' in region_data:
        W = region_data['soil_moisture']
        W_min = crop_params['soil_moisture_min']
        scores['moisture'] = min(1.0, W / W_min)
        details['moisture'] = f"Влага: {W:.2f} (мин: {W_min})"
    else:
        scores['moisture'] = 0.7  # Предполагаем среднее
        details['moisture'] = "Нет данных (принято 0.7)"

    # 6. Оценка радиации
    if 'radiation_sum' in region_data:
        Q = region_data['radiation_sum']
        Q_min = crop_params['radiation_min']
        if Q >= Q_min:
            scores['radiation'] = 1.0
            details['radiation'] = f"Достаточно ({Q:.0f} МДж/м²)"
        else:
            scores['radiation'] = Q / Q_min
            details['radiation'] = f"Недостаточно ({Q:.0f} / {Q_min})"
    else:
        scores['radiation'] = 0.7  # Предполагаем среднее
        details['radiation'] = "Нет данных"

    # 7. Оценка морозостойкости
    if 'temperature_min_winter' in region_data:
        T_min = region_data['temperature_min_winter']
        frost_tol = crop_params['frost_tolerance']

        if T_min >= frost_tol:
            scores['frost'] = 1.0
            details['frost'] = f"Морозы не опасны ({T_min:.1f}°C >= {frost_tol}°C)"
        else:
            deviation = abs(frost_tol - T_min)
            scores['frost'] = max(0, 1 - deviation / 10)
            details['frost'] = f"Риск вымерзания ({T_min:.1f}°C < {frost_tol}°C)"
    else:
        scores['frost'] = 0.8  # Предполагаем низкий риск
        details['frost'] = "Нет данных"

    # Взвешенная сумма
    final_score = sum(scores[k] * weights[k] for k in weights.keys())
    final_score_percent = final_score * 100

    # Интерпретация
    if final_score_percent >= 80:
        interpretation = "Высокая пригодность"
    elif final_score_percent >= 60:
        interpretation = "Хорошая пригодность"
    elif final_score_percent >= 40:
        interpretation = "Умеренная пригодность"
    else:
        interpretation = "Низкая пригодность"

    return {
        'crop': crop_name,
        'crop_name_ru': crop_params['name_ru'],
        'suitability_score': round(final_score_percent, 1),
        'interpretation': interpretation,
        'scores_breakdown': {k: round(v * 100, 1) for k, v in scores.items()},
        'details': details
    }


def rank_crops(region_data):
    """
    Ранжирование всех культур по пригодности

    Args:
        region_data: словарь с данными региона

    Returns:
        Список культур, отсортированный по убыванию пригодности
    """
    results = []

    for crop_name in CROP_PARAMETERS.keys():
        suitability = calculate_suitability_score(region_data, crop_name)
        if suitability:
            results.append(suitability)

    # Сортировка по убыванию рейтинга
    results.sort(key=lambda x: x['suitability_score'], reverse=True)

    return results


def get_top_n_crops(region_data, n=3):
    """
    Получение топ-N культур

    Args:
        region_data: словарь с данными региона
        n: количество культур

    Returns:
        Список топ-N культур
    """
    ranked = rank_crops(region_data)
    return ranked[:n]


def prepare_region_features(climate_data, soil_data, indices):
    """
    Подготовка данных региона для расчета пригодности

    Args:
        climate_data: климатические данные
        soil_data: почвенные данные
        indices: агрономические индексы

    Returns:
        Словарь с агрегированными данными
    """
    region_data = {}

    # Климатические параметры
    if climate_data:
        region_data['temperature_avg'] = np.mean(climate_data.get('temperature_avg', []))
        region_data['temperature_max'] = climate_data.get('temperature_max', 30)
        region_data['temperature_min'] = climate_data.get('temperature_min', -20)
        region_data['temperature_min_winter'] = climate_data.get('temperature_min', -10)

        region_data['precipitation_sum'] = climate_data.get('precipitation_sum', 0)
        region_data['precipitation_annual'] = climate_data.get('precipitation_sum', 0)

        region_data['radiation_sum'] = climate_data.get('radiation_sum', 0)

    # Почвенные параметры
    if soil_data:
        texture = soil_data.get('texture', {})
        region_data['soil_type'] = texture.get('texture_class', 'unknown')

    # Индексы
    if indices:
        if indices.get('gdd'):
            region_data['gdd'] = indices['gdd'].get('total_gdd', 0)

        if indices.get('gtk'):
            gtk_value = indices['gtk'].get('gtk')
            region_data['gtk'] = gtk_value

        if indices.get('spi'):
            spi_value = indices['spi'].get('latest_spi')
            region_data['spi'] = spi_value

        if indices.get('lai'):
            region_data['lai'] = indices['lai'].get('lai_estimated', 0)

    # Примерная оценка влажности почвы (если нет точных данных)
    if 'soil_moisture' not in region_data:
        # Используем косвенную оценку через ГТК
        gtk = region_data.get('gtk', 1.0)
        if gtk > 1.3:
            region_data['soil_moisture'] = 0.8
        elif gtk > 1.0:
            region_data['soil_moisture'] = 0.7
        elif gtk > 0.7:
            region_data['soil_moisture'] = 0.6
        else:
            region_data['soil_moisture'] = 0.5

    return region_data


def format_suitability_report(top_crops):
    """
    Форматирование отчета по пригодности культур

    Args:
        top_crops: список топ-культур

    Returns:
        Строка с форматированным отчетом
    """
    report = []

    report.append("🌾 РЕЙТИНГ ПРИГОДНОСТИ КУЛЬТУР:\n")

    for i, crop in enumerate(top_crops, 1):
        report.append(f"{i}. {crop['crop_name_ru']}")
        report.append(f"   📊 Пригодность: {crop['suitability_score']:.1f}% - {crop['interpretation']}")

        # Ключевые параметры
        breakdown = crop['scores_breakdown']
        top_params = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)[:3]

        report.append("   ✓ Сильные стороны:")
        for param, score in top_params:
            if score > 70:
                report.append(f"      • {param}: {score:.0f}%")

        report.append("")

    return "\n".join(report)
