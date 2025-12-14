"""
Модуль для работы с климатическими данными ERA5
Получает расширенный набор параметров для агрономического анализа
"""
import cdsapi
from config.settings import CDS_API_URL, CDS_API_KEY
import xarray as xr
import pandas as pd
import numpy as np
import os
import hashlib
from datetime import datetime, timedelta


def generate_filename(latitude, longitude, start_date_str, end_date_str, variables):
    """Генерирует уникальное имя файла на основе параметров запроса"""
    key_string = f"{latitude}_{longitude}_{start_date_str}_{end_date_str}_{'_'.join(sorted(variables))}"
    hash_key = hashlib.md5(key_string.encode()).hexdigest()
    filename = f"data/era5/climate_{hash_key}.nc"
    return filename


def calculate_vapor_deficit(T, Td):
    """
    Расчет дефицита влажности воздуха (гПа)

    Args:
        T: температура воздуха (°C)
        Td: точка росы (°C)

    Returns:
        Дефицит влажности (гПа)
    """
    # Формула Магнуса для насыщающей упругости водяного пара
    e_s = 6.112 * np.exp(17.67 * T / (T + 243.5))  # Насыщающая упругость
    e_a = 6.112 * np.exp(17.67 * Td / (Td + 243.5))  # Фактическая упругость
    d = e_s - e_a
    return d


def calculate_productive_moisture(theta, layer_depth, FC=0.35, PWP=0.15):
    """
    Расчет запасов продуктивной влаги (мм)

    Args:
        theta: объемная влажность почвы (м³/м³)
        layer_depth: глубина слоя (мм)
        FC: наименьшая влагоемкость (полевая влагоемкость)
        PWP: влажность завядания

    Returns:
        Запасы продуктивной влаги (мм)
    """
    W = (theta - PWP) / (FC - PWP) * layer_depth
    return max(0, W)


async def fetch_era5_extended_data(lat, lon, start_date, end_date):
    """
    Получает расширенный набор климатических данных из ERA5

    Параметры:
        1. 2m temperature (T_avg, T_max, T_min)
        2. Total precipitation (P)
        3. Surface solar radiation (Q)
        4. 2m dewpoint temperature - для расчета дефицита влажности
        5. Soil temperature (0-7 см, 7-28 см)
        6. Volumetric soil water (0-7 см, 7-28 см)

    Args:
        lat: широта
        lon: долгота
        start_date: начальная дата (строка 'YYYY-MM-DD' или datetime)
        end_date: конечная дата (строка 'YYYY-MM-DD' или datetime)

    Returns:
        Словарь с климатическими данными и расчетными параметрами
    """
    # Преобразование дат
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    # Запрашиваемые переменные
    variables = [
        '2m_temperature',
        'total_precipitation',
        'surface_solar_radiation_downwards',
        '2m_dewpoint_temperature',
        'soil_temperature_level_1',  # 0-7 см
        'soil_temperature_level_2',  # 7-28 см
        'volumetric_soil_water_layer_1',  # 0-7 см
        'volumetric_soil_water_layer_2'   # 7-28 см
    ]

    output_file = generate_filename(lat, lon, start_date_str, end_date_str, variables)

    # Генерируем диапазон дат
    date_range = pd.date_range(start=start_date, end=end_date)
    years = sorted(list(set([d.year for d in date_range])))
    months = sorted(list(set([d.month for d in date_range])))
    days = sorted(list(set([d.day for d in date_range])))

    try:
        # Создаем директорию если не существует
        os.makedirs('data/era5', exist_ok=True)

        # Проверяем кэш
        if not os.path.exists(output_file):
            print(f"Загрузка данных ERA5 для координат {lat}, {lon}...")
            c = cdsapi.Client(url=CDS_API_URL, key=CDS_API_KEY)

            # Запрос данных из ERA5-Land (суточная статистика)
            c.retrieve(
                'reanalysis-era5-land',
                {
                    'format': 'netcdf',
                    'variable': variables,
                    'year': [str(y) for y in years],
                    'month': [f'{m:02d}' for m in months],
                    'day': [f'{d:02d}' for d in days],
                    'time': ['00:00', '06:00', '12:00', '18:00'],
                    'area': [
                        round(lat + 0.25, 2), round(lon - 0.25, 2),
                        round(lat - 0.25, 2), round(lon + 0.25, 2),
                    ],  # North, West, South, East (сетка 0.5°)
                },
                output_file
            )
            print(f"Данные сохранены в {output_file}")

        # Обработка загруженного файла
        ds = xr.open_dataset(output_file, engine="netcdf4")

        # Извлечение данных
        # Температура воздуха (конвертация из K в °C)
        t2m = ds['t2m'].mean(dim=['latitude', 'longitude']).values - 273.15
        t2m_max = ds['t2m'].max(dim=['time', 'latitude', 'longitude']).values - 273.15
        t2m_min = ds['t2m'].min(dim=['time', 'latitude', 'longitude']).values - 273.15

        # Точка росы (конвертация из K в °C)
        td = ds['d2m'].mean(dim=['latitude', 'longitude']).values - 273.15

        # Осадки (конвертация из м в мм)
        tp = ds['tp'].sum(dim=['latitude', 'longitude']).values * 1000

        # Радиация (Дж/м² → МДж/м²)
        ssrd = ds['ssrd'].mean(dim=['latitude', 'longitude']).values / 1e6

        # Температура почвы (конвертация из K в °C)
        stl1 = ds['stl1'].mean(dim=['latitude', 'longitude']).values - 273.15
        stl2 = ds['stl2'].mean(dim=['latitude', 'longitude']).values - 273.15

        # Влажность почвы (м³/м³)
        swvl1 = ds['swvl1'].mean(dim=['latitude', 'longitude']).values
        swvl2 = ds['swvl2'].mean(dim=['latitude', 'longitude']).values

        # Временные метки
        time_values = ds['time'].values
        time_stamps = [pd.to_datetime(t).strftime('%Y-%m-%d') for t in time_values]

        # Группировка по дням (агрегация)
        df = pd.DataFrame({
            'time': pd.to_datetime(time_stamps),
            't2m': t2m,
            'td': td,
            'tp': tp,
            'ssrd': ssrd,
            'stl1': stl1,
            'stl2': stl2,
            'swvl1': swvl1,
            'swvl2': swvl2
        })

        daily = df.groupby(df['time'].dt.date).agg({
            't2m': 'mean',
            'td': 'mean',
            'tp': 'sum',
            'ssrd': 'sum',
            'stl1': 'mean',
            'stl2': 'mean',
            'swvl1': 'mean',
            'swvl2': 'mean'
        }).reset_index()

        # Расчет дефицита влажности
        daily['vapor_deficit'] = calculate_vapor_deficit(daily['t2m'], daily['td'])

        # Расчет запасов продуктивной влаги (для слоя 0-7 см)
        daily['productive_moisture'] = daily['swvl1'].apply(
            lambda x: calculate_productive_moisture(x, layer_depth=70)  # 70 мм = 7 см
        )

        # Формирование результата
        climate_data = {
            'dates': daily['time'].astype(str).tolist(),
            'temperature_avg': daily['t2m'].tolist(),
            'temperature_max': float(t2m_max),
            'temperature_min': float(t2m_min),
            'dewpoint': daily['td'].tolist(),
            'precipitation': daily['tp'].tolist(),
            'precipitation_sum': float(daily['tp'].sum()),
            'radiation': daily['ssrd'].tolist(),
            'radiation_sum': float(daily['ssrd'].sum()),
            'soil_temp_0_7cm': daily['stl1'].tolist(),
            'soil_temp_7_28cm': daily['stl2'].tolist(),
            'soil_moisture_0_7cm': daily['swvl1'].tolist(),
            'soil_moisture_7_28cm': daily['swvl2'].tolist(),
            'vapor_deficit': daily['vapor_deficit'].tolist(),
            'productive_moisture': daily['productive_moisture'].tolist()
        }

        ds.close()

        return climate_data

    except Exception as e:
        print(f"Ошибка при получении данных ERA5: {e}")
        import traceback
        traceback.print_exc()
        return None


# Обратная совместимость со старым методом
async def get_climate_data(latitude, longitude, start_date_str, end_date_str):
    """Обратная совместимость - упрощенная версия"""
    data = await fetch_era5_extended_data(latitude, longitude, start_date_str, end_date_str)

    if data:
        return {
            'daily': {
                'time': data['dates'],
                'temperature_2m_mean': data['temperature_avg'],
                'precipitation_sum': data['precipitation']
            }
        }
    return None
