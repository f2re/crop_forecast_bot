import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io

import xarray as xr

def plot_climate_data(netcdf_file_path):
    """
    Создает комбинированный график климатических данных из NetCDF файла.

    График включает:
    - Линию средней суточной температуры.
    - Закрашенную область между минимальной и максимальной температурой.
    - Столбчатую диаграмму суточных осадков.

    :param netcdf_file_path: Путь к NetCDF файлу с данными ERA5.
    :return: Байтовый объект с изображением графика или None в случае ошибки.
    """
    try:
        # Открываем NetCDF файл с помощью xarray
        with xr.open_dataset(netcdf_file_path) as ds:
            # Конвертируем в pandas DataFrame для удобства
            df = ds.to_dataframe()

            # Извлекаем данные. Названия переменных могут отличаться в зависимости от запроса.
            # Проверяем наличие нужных колонок
            temp_mean_col = 'mean_2m_air_temperature_daily'
            temp_max_col = 'maximum_2m_air_temperature_daily'
            temp_min_col = 'minimum_2m_air_temperature_daily'
            precip_col = 'sum_total_precipitation_daily'

            required_cols = [temp_mean_col, temp_max_col, temp_min_col, precip_col]
            if not all(col in df.columns for col in required_cols):
                # Попытка использовать альтернативные имена, если стандартные не найдены
                temp_mean_col = 't2m_mean'
                temp_max_col = 't2m_max'
                temp_min_col = 't2m_min'
                precip_col = 'tp_sum'
                required_cols = [temp_mean_col, temp_max_col, temp_min_col, precip_col]
                if not all(col in df.columns for col in required_cols):
                    return None # Возвращаем None, если данные не найдены

            # Конвертируем температуру из Кельвинов в Цельсии
            df[temp_mean_col] -= 273.15
            df[temp_max_col] -= 273.15
            df[temp_min_col] -= 273.15
            # Конвертируем осадки из метров в миллиметры
            df[precip_col] *= 1000

            fig, ax1 = plt.subplots(figsize=(12, 7))

            # График температуры
            ax1.set_xlabel('Дата')
            ax1.set_ylabel('Температура (°C)', color='tab:red')
            ax1.plot(df.index, df[temp_mean_col], color='tab:red', lw=2, label='Средняя температура')
            ax1.fill_between(df.index, df[temp_min_col], df[temp_max_col], color='tab:red', alpha=0.2, label='Диапазон (мин/макс)')
            ax1.tick_params(axis='y', labelcolor='tab:red')
            ax1.grid(axis='y', linestyle='--')

            # График осадков на второй оси
            ax2 = ax1.twinx()
            ax2.set_ylabel('Осадки (мм)', color='tab:blue')
            ax2.bar(df.index, df[precip_col], color='tab:blue', alpha=0.6, label='Осадки')
            ax2.tick_params(axis='y', labelcolor='tab:blue')

            # Настройка заголовка и легенды
            plt.title('Суточные климатические данные за период', pad=20)
            fig.tight_layout()
            plt.xticks(rotation=45)

            # Собираем легенду с обеих осей
            lines, labels = ax1.get_legend_handles_labels()
            bars, bar_labels = ax2.get_legend_handles_labels()
            ax2.legend(lines + bars, labels + bar_labels, loc='upper left')

            # Сохранение графика в байтовый объект
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)

            plt.close(fig)

            return buf
    except Exception as e:
        print(f"Ошибка при создании графика: {e}")
        return None
