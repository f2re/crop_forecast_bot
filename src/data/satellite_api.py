"""
Модуль для работы со спутниковыми данными
Использует Google Earth Engine для получения NDVI и LAI
"""
import ee
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# Флаг инициализации
_ee_initialized = False


def initialize_earth_engine():
    """Инициализация Google Earth Engine"""
    global _ee_initialized
    if not _ee_initialized:
        try:
            ee.Initialize()
            _ee_initialized = True
            print("Google Earth Engine успешно инициализирован")
        except Exception as e:
            print(f"Ошибка инициализации Earth Engine: {e}")
            print("Запустите: earthengine authenticate")
            raise


async def get_ndvi_timeseries(lat, lon, start_date, end_date):
    """
    Получение временного ряда NDVI из MODIS

    Использует MODIS Terra Vegetation Indices (MOD13Q1)
    - Разрешение: 250м
    - Частота: 16 дней
    - Диапазон NDVI: -1 до 1

    Args:
        lat: широта
        lon: долгота
        start_date: начальная дата (строка 'YYYY-MM-DD' или datetime)
        end_date: конечная дата (строка 'YYYY-MM-DD' или datetime)

    Returns:
        Список словарей с NDVI данными
    """
    initialize_earth_engine()

    # Преобразование дат
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    try:
        # Создание точки для анализа
        point = ee.Geometry.Point([lon, lat])

        # MODIS Terra Vegetation Indices 16-Day (250m)
        collection = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .filterDate(start_date_str, end_date_str) \
            .filterBounds(point)

        def extract_ndvi(image):
            """Извлечение NDVI для точки"""
            ndvi = image.select('NDVI').multiply(0.0001)  # Scale factor
            evi = image.select('EVI').multiply(0.0001)

            # Редукция к одной точке
            stats = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=250
            )

            evi_stats = evi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=250
            )

            return ee.Feature(None, {
                'ndvi': stats.get('NDVI'),
                'evi': evi_stats.get('EVI'),
                'date': image.date().format('YYYY-MM-dd')
            })

        # Применение функции ко всем изображениям
        ndvi_series = collection.map(extract_ndvi).getInfo()

        # Обработка результатов
        results = []
        for feature in ndvi_series['features']:
            props = feature['properties']
            if props['ndvi'] is not None:  # Пропускаем пустые значения
                results.append({
                    'date': props['date'],
                    'ndvi': float(props['ndvi']),
                    'evi': float(props['evi']) if props['evi'] is not None else None
                })

        print(f"Получено {len(results)} значений NDVI")
        return results

    except Exception as e:
        print(f"Ошибка получения NDVI: {e}")
        import traceback
        traceback.print_exc()
        return []


async def get_sentinel2_ndvi(lat, lon, start_date, end_date, cloud_threshold=20):
    """
    Получение NDVI из Sentinel-2 (более высокое разрешение)

    Sentinel-2:
    - Разрешение: 10м
    - Частота: ~5 дней
    - Лучшее качество, но может быть облачность

    Args:
        lat: широта
        lon: долгота
        start_date: начальная дата
        end_date: конечная дата
        cloud_threshold: максимальный процент облачности

    Returns:
        Список словарей с NDVI данными
    """
    initialize_earth_engine()

    # Преобразование дат
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    try:
        point = ee.Geometry.Point([lon, lat])

        # Sentinel-2 Surface Reflectance
        collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterDate(start_date_str, end_date_str) \
            .filterBounds(point) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_threshold))

        def calculate_ndvi(image):
            """Расчет NDVI для Sentinel-2"""
            # NDVI = (NIR - Red) / (NIR + Red)
            ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')

            stats = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=10
            )

            return ee.Feature(None, {
                'ndvi': stats.get('NDVI'),
                'date': image.date().format('YYYY-MM-dd'),
                'clouds': image.get('CLOUDY_PIXEL_PERCENTAGE')
            })

        ndvi_series = collection.map(calculate_ndvi).getInfo()

        results = []
        for feature in ndvi_series['features']:
            props = feature['properties']
            if props['ndvi'] is not None:
                results.append({
                    'date': props['date'],
                    'ndvi': float(props['ndvi']),
                    'cloud_cover': float(props['clouds'])
                })

        print(f"Получено {len(results)} значений NDVI из Sentinel-2")
        return results

    except Exception as e:
        print(f"Ошибка получения NDVI из Sentinel-2: {e}")
        import traceback
        traceback.print_exc()
        return []


async def get_lai_data(lat, lon, start_date, end_date):
    """
    Получение LAI (Leaf Area Index) из MODIS

    MODIS LAI/FPAR (MCD15A2H):
    - Разрешение: 500м
    - Частота: 8 дней

    Args:
        lat: широта
        lon: долгота
        start_date: начальная дата
        end_date: конечная дата

    Returns:
        Список словарей с LAI данными
    """
    initialize_earth_engine()

    # Преобразование дат
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    try:
        point = ee.Geometry.Point([lon, lat])

        # MODIS LAI/FPAR
        collection = ee.ImageCollection('MODIS/061/MCD15A2H') \
            .filterDate(start_date_str, end_date_str) \
            .filterBounds(point)

        def extract_lai(image):
            """Извлечение LAI"""
            lai = image.select('Lai').multiply(0.1)  # Scale factor
            fpar = image.select('Fpar').multiply(0.01)  # Scale factor

            lai_stats = lai.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=500
            )

            fpar_stats = fpar.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=500
            )

            return ee.Feature(None, {
                'lai': lai_stats.get('Lai'),
                'fpar': fpar_stats.get('Fpar'),
                'date': image.date().format('YYYY-MM-dd')
            })

        lai_series = collection.map(extract_lai).getInfo()

        results = []
        for feature in lai_series['features']:
            props = feature['properties']
            if props['lai'] is not None:
                results.append({
                    'date': props['date'],
                    'lai': float(props['lai']),
                    'fpar': float(props['fpar']) if props['fpar'] is not None else None
                })

        print(f"Получено {len(results)} значений LAI")
        return results

    except Exception as e:
        print(f"Ошибка получения LAI: {e}")
        import traceback
        traceback.print_exc()
        return []


async def get_satellite_summary(lat, lon, start_date, end_date):
    """
    Получение сводки спутниковых данных

    Возвращает агрегированные статистики за период

    Args:
        lat: широта
        lon: долгота
        start_date: начальная дата
        end_date: конечная дата

    Returns:
        Словарь со статистикой
    """
    # Получение данных
    ndvi_data = await get_ndvi_timeseries(lat, lon, start_date, end_date)
    lai_data = await get_lai_data(lat, lon, start_date, end_date)

    if not ndvi_data:
        print("Предупреждение: NDVI данные недоступны")
        return None

    # Преобразование в DataFrame для анализа
    df_ndvi = pd.DataFrame(ndvi_data)
    df_lai = pd.DataFrame(lai_data) if lai_data else None

    # Статистика NDVI
    ndvi_stats = {
        'ndvi_mean': float(df_ndvi['ndvi'].mean()),
        'ndvi_max': float(df_ndvi['ndvi'].max()),
        'ndvi_min': float(df_ndvi['ndvi'].min()),
        'ndvi_std': float(df_ndvi['ndvi'].std()),
        'ndvi_trend': float(np.polyfit(range(len(df_ndvi)), df_ndvi['ndvi'], 1)[0]),
        'ndvi_timeseries': ndvi_data
    }

    # Статистика LAI
    if df_lai is not None and len(df_lai) > 0:
        lai_stats = {
            'lai_mean': float(df_lai['lai'].mean()),
            'lai_max': float(df_lai['lai'].max()),
            'lai_min': float(df_lai['lai'].min()),
            'lai_timeseries': lai_data
        }
    else:
        lai_stats = {
            'lai_mean': None,
            'lai_max': None,
            'lai_min': None,
            'lai_timeseries': []
        }

    return {
        **ndvi_stats,
        **lai_stats,
        'data_availability': {
            'ndvi_count': len(ndvi_data),
            'lai_count': len(lai_data) if lai_data else 0
        }
    }
