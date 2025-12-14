"""
Модуль для расчета агрономических индексов
Включает GDD, SPI, ГТК, LAI
"""
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from scipy.stats import gamma, norm


def calculate_gdd(T_avg, T_base=10, T_upper=30):
    """
    Расчет GDD (Growing Degree Days) - суммы эффективных температур

    Формула: GDD = Σ max(0, min(T_avg - T_base, T_upper - T_base))

    Args:
        T_avg: массив или список среднесуточных температур (°C)
        T_base: биологический минимум (°C), по умолчанию 10°C
        T_upper: верхний порог (°C), по умолчанию 30°C

    Returns:
        dict с daily_gdd и cumulative_gdd
    """
    T_avg = np.array(T_avg)

    # Расчет дневных GDD
    gdd_daily = np.clip(T_avg - T_base, 0, T_upper - T_base)

    # Кумулятивная сумма
    gdd_cumulative = np.cumsum(gdd_daily)

    return {
        'daily_gdd': gdd_daily.tolist(),
        'cumulative_gdd': gdd_cumulative.tolist(),
        'total_gdd': float(gdd_cumulative[-1]) if len(gdd_cumulative) > 0 else 0
    }


# Требования культур по GDD
CROP_GDD_REQUIREMENTS = {
    'wheat': {
        'base': 5,
        'upper': 30,
        'total': 1800,
        'name_ru': 'Пшеница'
    },
    'corn': {
        'base': 10,
        'upper': 30,
        'total': 2700,
        'name_ru': 'Кукуруза'
    },
    'sunflower': {
        'base': 8,
        'upper': 34,
        'total': 2100,
        'name_ru': 'Подсолнечник'
    },
    'soybean': {
        'base': 10,
        'upper': 30,
        'total': 2500,
        'name_ru': 'Соя'
    },
    'barley': {
        'base': 5,
        'upper': 30,
        'total': 1500,
        'name_ru': 'Ячмень'
    },
    'rapeseed': {
        'base': 5,
        'upper': 30,
        'total': 2000,
        'name_ru': 'Рапс'
    },
    'potato': {
        'base': 7,
        'upper': 30,
        'total': 1400,
        'name_ru': 'Картофель'
    },
    'sugar_beet': {
        'base': 10,
        'upper': 30,
        'total': 2000,
        'name_ru': 'Сахарная свекла'
    }
}


def check_gdd_requirements(total_gdd, crop_name):
    """
    Проверка соответствия GDD требованиям культуры

    Args:
        total_gdd: накопленная сумма эффективных температур
        crop_name: название культуры

    Returns:
        dict с оценкой пригодности
    """
    if crop_name not in CROP_GDD_REQUIREMENTS:
        return {'suitable': None, 'message': 'Культура не найдена'}

    required_gdd = CROP_GDD_REQUIREMENTS[crop_name]['total']
    ratio = total_gdd / required_gdd

    if ratio >= 1.0:
        suitability = 'высокая'
        message = f'GDD достаточно для полного цикла ({total_gdd:.0f} / {required_gdd})'
    elif ratio >= 0.9:
        suitability = 'хорошая'
        message = f'GDD близко к требуемому ({total_gdd:.0f} / {required_gdd})'
    elif ratio >= 0.75:
        suitability = 'удовлетворительная'
        message = f'GDD ниже оптимального ({total_gdd:.0f} / {required_gdd})'
    else:
        suitability = 'низкая'
        message = f'GDD недостаточно ({total_gdd:.0f} / {required_gdd})'

    return {
        'suitable': suitability,
        'message': message,
        'ratio': ratio,
        'required_gdd': required_gdd,
        'actual_gdd': total_gdd
    }


def calculate_spi(precipitation_series, timescale=3):
    """
    Расчет SPI (Standardized Precipitation Index) для оценки засухи

    SPI использует гамма-распределение для стандартизации осадков

    Args:
        precipitation_series: массив месячных осадков (мм) за длительный период (мин. 30 лет)
        timescale: временная шкала (1, 3, 6, 12 месяцев)

    Returns:
        dict с SPI значениями и интерпретацией
    """
    precip = np.array(precipitation_series)

    # Скользящее суммирование
    if timescale > 1:
        rolling_precip = pd.Series(precip).rolling(window=timescale).sum().dropna()
    else:
        rolling_precip = pd.Series(precip)

    # Удаление нулевых значений для подбора распределения
    non_zero = rolling_precip[rolling_precip > 0]

    if len(non_zero) < 10:
        return {
            'spi_values': None,
            'latest_spi': None,
            'interpretation': 'Недостаточно данных для расчета SPI'
        }

    try:
        # Подбор параметров гамма-распределения
        shape, loc, scale = gamma.fit(non_zero, floc=0)

        # Кумулятивная вероятность
        cdf = gamma.cdf(rolling_precip, shape, loc, scale)

        # Обработка краевых случаев
        cdf = np.clip(cdf, 0.001, 0.999)

        # Преобразование в стандартное нормальное распределение
        spi_values = norm.ppf(cdf)

        # Замена NaN на 0
        spi_values = np.nan_to_num(spi_values, nan=0.0)

        latest_spi = float(spi_values[-1])

        return {
            'spi_values': spi_values.tolist(),
            'latest_spi': latest_spi,
            'interpretation': interpret_spi(latest_spi),
            'timescale': timescale
        }

    except Exception as e:
        print(f"Ошибка расчета SPI: {e}")
        return {
            'spi_values': None,
            'latest_spi': None,
            'interpretation': 'Ошибка расчета'
        }


def interpret_spi(spi_value):
    """Интерпретация значения SPI"""
    if spi_value is None:
        return "Нет данных"
    elif spi_value >= 2.0:
        return "Экстремально влажно"
    elif spi_value >= 1.5:
        return "Очень влажно"
    elif spi_value >= 1.0:
        return "Умеренно влажно"
    elif spi_value >= -1.0:
        return "Норма"
    elif spi_value >= -1.5:
        return "Умеренная засуха"
    elif spi_value >= -2.0:
        return "Сильная засуха"
    else:
        return "Экстремальная засуха"


def calculate_gtk(precipitation_sum, temperature_sum_above_10):
    """
    Расчет ГТК (Гидротермический коэффициент Селянинова)

    ГТК = Σ осадков / (0.1 × Σ T>10°C)

    Интерпретация:
    > 1.3 - избыточное увлажнение
    1.0-1.3 - оптимальное
    0.7-1.0 - недостаточное
    < 0.7 - засуха

    Args:
        precipitation_sum: сумма осадков за период (мм)
        temperature_sum_above_10: сумма активных температур >10°C

    Returns:
        dict с ГТК и интерпретацией
    """
    if temperature_sum_above_10 <= 0:
        return {
            'gtk': None,
            'interpretation': 'Недостаточно данных (нет температур >10°C)'
        }

    gtk = precipitation_sum / (0.1 * temperature_sum_above_10)

    return {
        'gtk': round(gtk, 2),
        'interpretation': interpret_gtk(gtk),
        'precipitation_sum': precipitation_sum,
        'temperature_sum': temperature_sum_above_10
    }


def interpret_gtk(gtk_value):
    """Интерпретация значения ГТК"""
    if gtk_value is None:
        return "Нет данных"
    elif gtk_value > 1.6:
        return "Избыточное увлажнение"
    elif gtk_value >= 1.3:
        return "Повышенное увлажнение"
    elif gtk_value >= 1.0:
        return "Оптимальное увлажнение"
    elif gtk_value >= 0.7:
        return "Недостаточное увлажнение"
    elif gtk_value >= 0.5:
        return "Засушливые условия"
    else:
        return "Сильная засуха"


def estimate_lai_from_ndvi(ndvi):
    """
    Оценка LAI (Leaf Area Index) из NDVI

    Эмпирическая связь LAI с NDVI (Baret et al., 1989)
    LAI = -ln((0.69 - NDVI) / 0.59) / 0.91

    Args:
        ndvi: значение NDVI (может быть массивом)

    Returns:
        Значение или массив LAI
    """
    ndvi = np.array(ndvi)

    # Формула Baret
    # Защита от выхода за пределы
    ndvi_clipped = np.clip(ndvi, -0.2, 0.68)

    numerator = 0.69 - ndvi_clipped
    denominator = 0.59

    # Избегаем отрицательных значений под логарифмом
    ratio = np.maximum(numerator / denominator, 0.001)

    lai = -np.log(ratio) / 0.91

    # Ограничение физическими пределами (0-8)
    lai = np.clip(lai, 0, 8)

    return lai


def calculate_par_absorption(lai):
    """
    Расчет поглощения ФАР (фотосинтетически активной радиации)

    FPAR = 1 - exp(-k × LAI)
    k - коэффициент экстинкции света (≈0.5 для большинства культур)

    Args:
        lai: Leaf Area Index

    Returns:
        FPAR (доля поглощенной ФАР, 0-1)
    """
    k = 0.5  # Коэффициент экстинкции
    fpar = 1 - np.exp(-k * np.array(lai))

    return fpar


def calculate_all_indices(climate_data, ndvi_data=None):
    """
    Расчет всех агрономических индексов для региона

    Args:
        climate_data: словарь с климатическими данными
        ndvi_data: список значений NDVI (опционально)

    Returns:
        dict со всеми индексами
    """
    results = {}

    # 1. GDD
    if 'temperature_avg' in climate_data:
        temps = climate_data['temperature_avg']
        gdd_result = calculate_gdd(temps, T_base=10, T_upper=30)
        results['gdd'] = gdd_result

        # Расчет суммы активных температур >10°C для ГТК
        temps_array = np.array(temps)
        active_temps = temps_array[temps_array > 10]
        temp_sum_above_10 = float(np.sum(active_temps - 10))
    else:
        results['gdd'] = None
        temp_sum_above_10 = 0

    # 2. ГТК
    if 'precipitation_sum' in climate_data and temp_sum_above_10 > 0:
        precip_sum = climate_data['precipitation_sum']
        gtk_result = calculate_gtk(precip_sum, temp_sum_above_10)
        results['gtk'] = gtk_result
    else:
        results['gtk'] = None

    # 3. SPI (требует длительный ряд данных)
    if 'precipitation' in climate_data:
        precip_series = climate_data['precipitation']
        if len(precip_series) >= 12:  # Минимум год данных
            spi_result = calculate_spi(precip_series, timescale=3)
            results['spi'] = spi_result
        else:
            results['spi'] = {'interpretation': 'Недостаточно данных (нужен год+)'}
    else:
        results['spi'] = None

    # 4. LAI из NDVI
    if ndvi_data:
        ndvi_values = [d['ndvi'] for d in ndvi_data if 'ndvi' in d]
        if ndvi_values:
            ndvi_mean = np.mean(ndvi_values)
            lai = float(estimate_lai_from_ndvi(ndvi_mean))
            fpar = float(calculate_par_absorption(lai))

            results['lai'] = {
                'lai_estimated': round(lai, 2),
                'fpar': round(fpar, 2),
                'ndvi_mean': round(ndvi_mean, 3),
                'based_on': 'NDVI данные'
            }
        else:
            results['lai'] = None
    else:
        results['lai'] = None

    return results


def get_indices_summary(indices):
    """
    Формирование текстового резюме по индексам

    Args:
        indices: результат calculate_all_indices

    Returns:
        Строка с резюме
    """
    summary = []

    summary.append("📊 АГРОНОМИЧЕСКИЕ ИНДЕКСЫ:\n")

    # GDD
    if indices.get('gdd'):
        gdd = indices['gdd']
        summary.append(f"🌡️ GDD (сумма эффективных температур): {gdd['total_gdd']:.0f}°C·дни")

    # ГТК
    if indices.get('gtk'):
        gtk = indices['gtk']
        summary.append(f"💧 ГТК (увлажнение): {gtk['gtk']} - {gtk['interpretation']}")

    # SPI
    if indices.get('spi') and indices['spi'].get('latest_spi') is not None:
        spi = indices['spi']
        summary.append(f"☔ SPI (засуха): {spi['latest_spi']:.2f} - {spi['interpretation']}")

    # LAI
    if indices.get('lai'):
        lai = indices['lai']
        summary.append(f"🌿 LAI (площадь листьев): {lai['lai_estimated']} (FPAR: {lai['fpar']*100:.0f}%)")

    return "\n".join(summary)
