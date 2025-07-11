import cdsapi
from config.settings import CDS_API_URL, CDS_API_KEY
import xarray as xr
import pandas as pd
import os
import hashlib
from datetime import datetime

def generate_filename(latitude, longitude, start_date_str, end_date_str, variables):
    """
    Генерирует уникальное имя файла на основе параметров запроса.
    """
    key_string = f"{latitude}_{longitude}_{start_date_str}_{end_date_str}_{'_'.join(sorted(variables))}"
    hash_key = hashlib.md5(key_string.encode()).hexdigest()
    filename = f"data/era5/download_{hash_key}.nc"
    return filename

def get_climate_data(latitude, longitude, start_date_str, end_date_str):
    """
    Получает агрегированные суточные климатические данные из Copernicus Climate Data Store (CDS).

    Эта функция запрашивает дневные статистики (минимальная, максимальная, средняя температура и сумма осадков)
    за указанный период и кэширует результат в NetCDF файл.

    :param latitude: Широта
    :param longitude: Долгота
    :param start_date_str: Начальная дата в формате 'YYYY-MM-DD'
    :param end_date_str: Конечная дата в формате 'YYYY-MM-DD'
    :return: Словарь с данными о погоде или None в случае ошибки.
    """
    # Запрашиваемые переменные и статистики
    variables = ['2m_temperature', 'total_precipitation']
    output_file = generate_filename(latitude, longitude, start_date_str, end_date_str, variables)

    # Генерируем полный диапазон дат для запроса
    date_range = pd.date_range(start=start_date_str, end=end_date_str)
    years = sorted(list(set([d.year for d in date_range])))
    months = sorted(list(set([d.month for d in date_range])))
    days = sorted(list(set([d.day for d in date_range])))

    try:
        # Проверяем, существует ли уже кэшированный файл
        if not os.path.exists(output_file):
            c = cdsapi.Client(url=CDS_API_URL, key=CDS_API_KEY)
            c.retrieve(
                'derived-era5-single-levels-daily-statistics',
                {
                    'format': 'netcdf',
                    'variable': variables,
                    'statistic': [
                        'daily_mean', 'daily_maximum', 'daily_minimum', 'daily_sum'
                    ],
                    'year': [str(y) for y in years],
                    'month': [f'{m:02d}' for m in months],
                    'day': [f'{d:02d}' for d in days],
                    'area': [
                        round(latitude, 2), round(longitude, 2),
                        round(latitude, 2), round(longitude, 2),
                    ],  # North, West, South, East
                    'format': 'netcdf',
                    "download_format": "unarchived"
                },
                output_file)

        # Обработка загруженного файла с явным указанием движка
        ds = xr.open_dataset(output_file, engine="netcdf4")
        # Выводим информацию о структуре данных для отладки
        print(f"Доступные переменные в наборе данных: {list(ds.variables)}")
        print(f"Размерности набора данных: {list(ds.dims)}")
        
        # Проверяем наличие нужных переменных
        if 't2m' not in ds and '2m_temperature' not in ds:
            t2m_var = None
            for var in ds.variables:
                if 'temp' in var.lower() or 't2m' in var.lower():
                    t2m_var = var
                    break
            if t2m_var is None:
                raise ValueError("Файл не содержит переменных температуры.")
        else:
            t2m_var = 't2m' if 't2m' in ds else '2m_temperature'
            
        if 'tp' not in ds and 'total_precipitation' not in ds:
            tp_var = None
            for var in ds.variables:
                if 'precip' in var.lower() or 'tp' in var.lower():
                    tp_var = var
                    break
            if tp_var is None:
                raise ValueError("Файл не содержит переменных осадков.")
        else:
            tp_var = 'tp' if 'tp' in ds else 'total_precipitation'
            
        print(f"Используем переменные: температура={t2m_var}, осадки={tp_var}")
        
        # Находим временную размерность
        time_dim = None
        for dim in ds.dims:
            if dim.lower() == 'time' or 'time' in str(ds[dim].attrs).lower():
                time_dim = dim
                break
                
        if not time_dim:
            # Если не нашли явную размерность времени, пробуем найти координату с временными метками
            for var in ds.variables:
                if hasattr(ds[var], 'attrs') and 'units' in ds[var].attrs:
                    if 'since' in ds[var].attrs['units'].lower():
                        time_dim = var
                        break
                        
        if not time_dim:
            # Если всё еще не нашли, берем первую координату как время
            for coord in ds.coords:
                if len(ds[coord].shape) <= 1:  # Обычно временная координата одномерная
                    time_dim = coord
                    print(f"Используем координату {coord} как временную")
                    break
        
        print(f"Используем измерение времени: {time_dim}")
        
        # Получаем временные метки
        if time_dim:
            # Пытаемся преобразовать значения в datetime
            try:
                time_values = ds[time_dim].values
                time_stamps = [pd.to_datetime(t).strftime('%Y-%m-%d') for t in time_values]
            except (TypeError, ValueError):
                # Если не удалось, используем индексы как дни начиная с start_date
                time_stamps = [(start_date + pd.Timedelta(days=i)).strftime('%Y-%m-%d') 
                               for i in range(len(ds[time_dim]))]                
        else:
            # Если не нашли временную размерность, используем диапазон дат из запроса
            date_range = pd.date_range(start=start_date, end=end_date)
            time_stamps = [d.strftime('%Y-%m-%d') for d in date_range]
        
        # Температура из Кельвинов в Цельсии
        temps = ds[t2m_var]
        if hasattr(temps, 'units') and 'k' in temps.units.lower():
            # Если в Кельвинах, конвертируем в Цельсии
            temperatures = (temps.values - 273.15).flatten().tolist()
        else:
            # Предполагаем, что уже в Цельсиях
            temperatures = temps.values.flatten().tolist()
            
        # Осадки из метров в миллиметры, если необходимо
        precips = ds[tp_var]
        if hasattr(precips, 'units') and 'm' in precips.units.lower() and 'mm' not in precips.units.lower():
            # Если в метрах, конвертируем в миллиметры
            precipitations = (precips.values * 1000).flatten().tolist()
        else:
            # Предполагаем, что уже в мм или правильных единицах
            precipitations = precips.values.flatten().tolist()

        climate_data = {
            'daily': {
                'time': time_stamps,
                'temperature_2m_mean': temperatures,
                'precipitation_sum': precipitations
            }
        }
        return climate_data

    except Exception as e:
        print(f"Ошибка при обработке данных ERA5: {e}")
        return None
