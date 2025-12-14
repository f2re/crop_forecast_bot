"""
Модуль для расчета экономики и рисков выращивания культур
"""
import numpy as np


# Региональные затраты на выращивание культур (₽/га)
# Данные примерные, для разных регионов России (2024г.)
REGIONAL_COSTS = {
    'wheat': {
        'seeds': 3500,
        'fertilizers': 8000,
        'fuel': 4500,
        'pesticides': 2000,
        'machinery': 3000,
        'labor': 2500,
        'other': 1500
    },
    'corn': {
        'seeds': 6000,
        'fertilizers': 12000,
        'fuel': 5500,
        'pesticides': 3000,
        'machinery': 4000,
        'labor': 3000,
        'other': 2000
    },
    'sunflower': {
        'seeds': 4500,
        'fertilizers': 7000,
        'fuel': 5000,
        'pesticides': 2500,
        'machinery': 3500,
        'labor': 2500,
        'other': 1500
    },
    'soybean': {
        'seeds': 5000,
        'fertilizers': 6000,  # Меньше азота из-за азотфиксации
        'fuel': 5000,
        'pesticides': 3500,
        'machinery': 3500,
        'labor': 2500,
        'other': 1500
    },
    'barley': {
        'seeds': 3000,
        'fertilizers': 7000,
        'fuel': 4000,
        'pesticides': 1800,
        'machinery': 2800,
        'labor': 2200,
        'other': 1200
    },
    'rapeseed': {
        'seeds': 3500,
        'fertilizers': 10000,
        'fuel': 5500,
        'pesticides': 4000,
        'machinery': 3800,
        'labor': 2800,
        'other': 1800
    },
    'potato': {
        'seeds': 25000,
        'fertilizers': 15000,
        'fuel': 8000,
        'pesticides': 5000,
        'machinery': 6000,
        'labor': 8000,
        'other': 3000
    },
    'sugar_beet': {
        'seeds': 8000,
        'fertilizers': 12000,
        'fuel': 7000,
        'pesticides': 4500,
        'machinery': 5000,
        'labor': 6000,
        'other': 2500
    }
}


# Средние цены реализации (₽/т, 2024г.)
MARKET_PRICES = {
    'wheat': 15000,
    'corn': 14000,
    'sunflower': 30000,
    'soybean': 35000,
    'barley': 13000,
    'rapeseed': 32000,
    'potato': 20000,
    'sugar_beet': 3500
}


# Средняя урожайность по России (ц/га)
AVERAGE_YIELDS = {
    'wheat': 35,
    'corn': 55,
    'sunflower': 25,
    'soybean': 20,
    'barley': 32,
    'rapeseed': 28,
    'potato': 250,
    'sugar_beet': 450
}


def estimate_yield(crop_name, suitability_score, indices):
    """
    Оценка потенциальной урожайности на основе пригодности

    Args:
        crop_name: название культуры
        suitability_score: оценка пригодности (0-100)
        indices: агрономические индексы

    Returns:
        Прогнозная урожайность (ц/га)
    """
    if crop_name not in AVERAGE_YIELDS:
        return None

    base_yield = AVERAGE_YIELDS[crop_name]

    # Коэффициент пригодности (0.5 - 1.2)
    suitability_factor = 0.5 + (suitability_score / 100) * 0.7

    # Корректировка по ГТК (увлажнение)
    gtk_factor = 1.0
    if indices.get('gtk'):
        gtk = indices['gtk'].get('gtk', 1.0)
        if 1.0 <= gtk <= 1.5:
            gtk_factor = 1.1  # Оптимальное увлажнение, +10%
        elif gtk < 0.7:
            gtk_factor = 0.8  # Засуха, -20%
        elif gtk > 1.8:
            gtk_factor = 0.9  # Переувлажнение, -10%

    # Корректировка по GDD
    gdd_factor = 1.0
    if indices.get('gdd'):
        from .indices import CROP_GDD_REQUIREMENTS
        if crop_name in CROP_GDD_REQUIREMENTS:
            required_gdd = CROP_GDD_REQUIREMENTS[crop_name]['total']
            actual_gdd = indices['gdd'].get('total_gdd', 0)
            gdd_ratio = actual_gdd / required_gdd

            if gdd_ratio >= 1.0:
                gdd_factor = 1.0
            elif gdd_ratio >= 0.9:
                gdd_factor = 0.95
            elif gdd_ratio >= 0.8:
                gdd_factor = 0.85
            else:
                gdd_factor = 0.7

    # Корректировка по SPI (засуха)
    spi_factor = 1.0
    if indices.get('spi') and indices['spi'].get('latest_spi') is not None:
        spi = indices['spi']['latest_spi']
        if spi < -1.5:
            spi_factor = 0.75  # Сильная засуха, -25%
        elif spi < -1.0:
            spi_factor = 0.9  # Умеренная засуха, -10%
        elif spi > 1.5:
            spi_factor = 0.95  # Переувлажнение, -5%

    # Итоговая урожайность
    estimated_yield = base_yield * suitability_factor * gtk_factor * gdd_factor * spi_factor

    return round(estimated_yield, 1)


def calculate_profitability(crop_name, yield_forecast, region='default'):
    """
    Расчет рентабельности выращивания культуры

    Args:
        crop_name: название культуры
        yield_forecast: прогнозная урожайность (ц/га)
        region: регион (для корректировки затрат)

    Returns:
        Словарь с экономическими показателями
    """
    if crop_name not in REGIONAL_COSTS or crop_name not in MARKET_PRICES:
        return None

    # Затраты
    costs = REGIONAL_COSTS[crop_name]
    total_costs = sum(costs.values())

    # Цена реализации
    price_per_ton = MARKET_PRICES[crop_name]

    # Выручка
    yield_tons = yield_forecast / 10  # ц/га -> т/га
    revenue = yield_tons * price_per_ton

    # Прибыль
    profit = revenue - total_costs

    # ROI (Return on Investment)
    roi = (profit / total_costs * 100) if total_costs > 0 else 0

    # Рентабельность
    profitability = (profit / revenue * 100) if revenue > 0 else 0

    # Точка безубыточности (мин. урожайность)
    breakeven_yield = (total_costs / price_per_ton) * 10  # т/га -> ц/га

    return {
        'costs': {
            'total': round(total_costs, 0),
            'breakdown': {k: round(v, 0) for k, v in costs.items()}
        },
        'revenue': round(revenue, 0),
        'profit': round(profit, 0),
        'roi_percent': round(roi, 1),
        'profitability_percent': round(profitability, 1),
        'breakeven_yield_cwt_per_ha': round(breakeven_yield, 1),
        'price_per_ton': price_per_ton,
        'yield_tons_per_ha': round(yield_tons, 2)
    }


def assess_climate_risks(climate_data, indices, crop_name):
    """
    Оценка климатических рисков (0-100, где 100 = максимальный риск)

    Args:
        climate_data: климатические данные
        indices: агрономические индексы
        crop_name: название культуры

    Returns:
        Словарь с оценкой рисков
    """
    risk_scores = {}

    # 1. Риск засухи (на основе SPI)
    if indices.get('spi') and indices['spi'].get('latest_spi') is not None:
        spi = indices['spi']['latest_spi']
        if spi < -2.0:
            risk_scores['drought'] = 90
        elif spi < -1.5:
            risk_scores['drought'] = 60
        elif spi < -1.0:
            risk_scores['drought'] = 30
        else:
            risk_scores['drought'] = 10
    else:
        risk_scores['drought'] = 20  # Умеренный риск по умолчанию

    # 2. Риск заморозков
    if climate_data and 'temperature_min' in climate_data:
        from .crop_suitability import CROP_PARAMETERS

        T_min = climate_data['temperature_min']

        if crop_name in CROP_PARAMETERS:
            frost_tolerance = CROP_PARAMETERS[crop_name]['frost_tolerance']

            if T_min < frost_tolerance - 5:
                risk_scores['frost'] = 80
            elif T_min < frost_tolerance:
                risk_scores['frost'] = 50
            elif T_min < frost_tolerance + 2:
                risk_scores['frost'] = 20
            else:
                risk_scores['frost'] = 5
        else:
            risk_scores['frost'] = 20
    else:
        risk_scores['frost'] = 15

    # 3. Риск переувлажнения
    if indices.get('gtk'):
        gtk = indices['gtk'].get('gtk', 1.0)
        if gtk > 2.0:
            risk_scores['excess_moisture'] = 70
        elif gtk > 1.6:
            risk_scores['excess_moisture'] = 40
        else:
            risk_scores['excess_moisture'] = 10
    else:
        risk_scores['excess_moisture'] = 15

    # 4. Риск недостатка тепла (GDD)
    if indices.get('gdd'):
        from .indices import CROP_GDD_REQUIREMENTS

        if crop_name in CROP_GDD_REQUIREMENTS:
            required_gdd = CROP_GDD_REQUIREMENTS[crop_name]['total']
            actual_gdd = indices['gdd'].get('total_gdd', 0)
            ratio = actual_gdd / required_gdd

            if ratio < 0.75:
                risk_scores['heat_deficit'] = 80
            elif ratio < 0.9:
                risk_scores['heat_deficit'] = 50
            elif ratio < 1.0:
                risk_scores['heat_deficit'] = 20
            else:
                risk_scores['heat_deficit'] = 5
        else:
            risk_scores['heat_deficit'] = 20
    else:
        risk_scores['heat_deficit'] = 25

    # Взвешенная сумма рисков
    weights = {
        'drought': 0.35,
        'frost': 0.25,
        'excess_moisture': 0.20,
        'heat_deficit': 0.20
    }

    total_risk = sum(risk_scores[k] * weights[k] for k in weights.keys())

    # Интерпретация
    if total_risk < 20:
        interpretation = "Низкий риск"
        recommendation = "Условия благоприятные для выращивания"
    elif total_risk < 40:
        interpretation = "Умеренный риск"
        recommendation = "Рекомендуется стандартная агротехника"
    elif total_risk < 60:
        interpretation = "Повышенный риск"
        recommendation = "Требуются дополнительные меры защиты"
    else:
        interpretation = "Высокий риск"
        recommendation = "Рекомендуется рассмотреть альтернативные культуры"

    return {
        'total_risk': round(total_risk, 1),
        'interpretation': interpretation,
        'recommendation': recommendation,
        'risk_breakdown': {k: round(v, 1) for k, v in risk_scores.items()}
    }


def calculate_final_rating(suitability_score, profitability, risk_assessment):
    """
    Расчет финального рейтинга культуры (0-100)

    Формула взвешенной суммы:
    Rating = 0.4 × Пригодность + 0.4 × Рентабельность + 0.2 × (100 - Риск)

    Args:
        suitability_score: оценка пригодности (0-100)
        profitability: словарь с экономическими показателями
        risk_assessment: словарь с оценкой рисков

    Returns:
        Финальный рейтинг
    """
    # Нормализация рентабельности (ROI) к шкале 0-100
    roi = profitability.get('roi_percent', 0)
    profit_score = min(100, max(0, 50 + roi))  # ROI 0% = 50, ROI 50% = 100

    # Риск (инвертируем, чтобы низкий риск = высокий балл)
    risk = risk_assessment.get('total_risk', 50)
    risk_score = 100 - risk

    # Взвешенная сумма
    rating = (
        0.4 * suitability_score +
        0.4 * profit_score +
        0.2 * risk_score
    )

    return round(rating, 1)


def format_economics_report(crop_name, profitability, risk_assessment):
    """
    Форматирование экономического отчета

    Args:
        crop_name: название культуры
        profitability: экономические показатели
        risk_assessment: оценка рисков

    Returns:
        Форматированный отчет
    """
    from .crop_suitability import CROP_PARAMETERS

    crop_name_ru = CROP_PARAMETERS.get(crop_name, {}).get('name_ru', crop_name)

    lines = []

    lines.append(f"💰 ЭКОНОМИКА: {crop_name_ru}\n")

    # Затраты
    costs = profitability['costs']
    lines.append(f"Затраты: {costs['total']:,.0f} ₽/га")
    lines.append(f"  • Семена: {costs['breakdown']['seeds']:,.0f} ₽")
    lines.append(f"  • Удобрения: {costs['breakdown']['fertilizers']:,.0f} ₽")
    lines.append(f"  • ГСМ: {costs['breakdown']['fuel']:,.0f} ₽")
    lines.append(f"  • СЗР: {costs['breakdown']['pesticides']:,.0f} ₽")

    # Выручка и прибыль
    lines.append(f"\nВыручка: {profitability['revenue']:,.0f} ₽/га")
    lines.append(f"Прибыль: {profitability['profit']:,.0f} ₽/га")

    # ROI
    roi = profitability['roi_percent']
    if roi > 0:
        lines.append(f"ROI: {roi:.1f}% ✅")
    else:
        lines.append(f"ROI: {roi:.1f}% ⚠️")

    # Точка безубыточности
    lines.append(f"\nТочка безубыточности: {profitability['breakeven_yield_cwt_per_ha']:.1f} ц/га")

    # Риски
    lines.append(f"\n⚠️ РИСКИ: {risk_assessment['interpretation']}")
    lines.append(f"Общий риск: {risk_assessment['total_risk']:.0f}/100")

    breakdown = risk_assessment['risk_breakdown']
    if breakdown.get('drought', 0) > 30:
        lines.append(f"  • Засуха: {breakdown['drought']:.0f}")
    if breakdown.get('frost', 0) > 30:
        lines.append(f"  • Заморозки: {breakdown['frost']:.0f}")
    if breakdown.get('excess_moisture', 0) > 30:
        lines.append(f"  • Переувлажнение: {breakdown['excess_moisture']:.0f}")

    lines.append(f"\n{risk_assessment['recommendation']}")

    return "\n".join(lines)
