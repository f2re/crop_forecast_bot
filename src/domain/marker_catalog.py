from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HazardFamily = Literal[
    "wind",
    "convective",
    "precipitation",
    "visibility",
    "icing",
    "temperature",
    "fire",
    "snow",
    "agro_temperature",
    "agro_moisture",
    "agro_wind",
    "agro_winter",
]
HazardScreeningStatus = Literal["model_screening", "catalog_only"]
HazardSourceStatus = Literal[
    "active_typical_list",
    "expired_experimental_reference",
]
PestMarkerStatus = Literal["implemented", "candidate_unlinked", "context_only"]
PestMarkerRole = Literal[
    "weather_driver",
    "biofix",
    "calculation",
    "quality",
    "context",
]


@dataclass(frozen=True, slots=True)
class HazardSource:
    key: str
    title: str
    url: str
    status: HazardSourceStatus
    status_note: str


@dataclass(frozen=True, slots=True)
class HazardType:
    code: str
    key: str
    name_ru: str
    family: HazardFamily
    screening_status: HazardScreeningStatus
    screening_inputs: tuple[str, ...]
    source_key: str
    operational_note: str


@dataclass(frozen=True, slots=True)
class PestMarker:
    key: str
    name_ru: str
    role: PestMarkerRole
    status: PestMarkerStatus
    weather_dependent: bool
    unit_or_form: str
    description: str
    operational_note: str


METEOROLOGICAL_HAZARD_SOURCE = HazardSource(
    key="rd_52_27_724_2019",
    title="РД 52.27.724-2019. Наставление по краткосрочным прогнозам погоды",
    url="https://method.meteorf.ru/norma/rd_52_27_724_2019.pdf",
    status="active_typical_list",
    status_note=(
        "Типовой перечень является рекомендуемым. Конкретные критерии ОЯ "
        "уточняются территориальными УГМС с учётом климата региона."
    ),
)

AGROMETEOROLOGICAL_HAZARD_REFERENCE = HazardSource(
    key="r_52_33_877_2019",
    title="Р 52.33.877-2019. Оценка опасных агрометеорологических явлений",
    url="https://files.stroyinf.ru/Data2/1/4293728/4293728665.pdf",
    status="expired_experimental_reference",
    status_note=(
        "Рекомендации действовали в опытной эксплуатации до 01.01.2022. "
        "Каталог использует их как научно-методическую историческую основу, "
        "но не как действующий источник официального предупреждения."
    ),
)

HAZARD_SOURCES: dict[str, HazardSource] = {
    source.key: source
    for source in (
        METEOROLOGICAL_HAZARD_SOURCE,
        AGROMETEOROLOGICAL_HAZARD_REFERENCE,
    )
}


METEOROLOGICAL_HAZARDS: tuple[HazardType, ...] = (
    HazardType(
        "A.1",
        "very_strong_wind",
        "Очень сильный ветер",
        "wind",
        "model_screening",
        ("maximum_wind_speed", "wind_gust"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Бот показывает только ранний модельный сигнал по ветру.",
    ),
    HazardType(
        "A.2",
        "hurricane_wind",
        "Ураганный ветер",
        "wind",
        "model_screening",
        ("maximum_wind_speed", "wind_gust"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Статус ОЯ подтверждается только официальным предупреждением.",
    ),
    HazardType(
        "A.3",
        "squall",
        "Шквал",
        "convective",
        "catalog_only",
        ("minute_wind_change", "wind_gust", "radar_convection"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Суточный порыв не позволяет распознать шквал как кратковременный процесс.",
    ),
    HazardType(
        "A.4",
        "tornado",
        "Смерч",
        "convective",
        "catalog_only",
        ("official_warning", "radar_rotation", "verified_observation"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "По CAPE или одному численному прогнозу смерч не диагностируется.",
    ),
    HazardType(
        "A.5",
        "very_heavy_rain",
        "Очень сильный дождь и смешанные осадки",
        "precipitation",
        "model_screening",
        ("precipitation_amount", "accumulation_period", "precipitation_type"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Модельный экран осадков не является штормовым предупреждением.",
    ),
    HazardType(
        "A.6",
        "strong_shower",
        "Сильный ливень",
        "convective",
        "catalog_only",
        ("hourly_precipitation", "radar_rain_rate", "accumulation_period"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Для надёжного наукастинга нужны почасовые данные и радиолокатор.",
    ),
    HazardType(
        "A.7",
        "prolonged_heavy_rain",
        "Продолжительный сильный дождь",
        "precipitation",
        "catalog_only",
        ("multi_day_precipitation", "rain_break_duration"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Требуется непрерывный многосуточный ряд и региональный критерий.",
    ),
    HazardType(
        "A.8",
        "very_heavy_snow",
        "Очень сильный снег",
        "precipitation",
        "catalog_only",
        ("snow_water_equivalent", "accumulation_period", "precipitation_type"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "В базовом контуре снег по официальным критериям не оценивается.",
    ),
    HazardType(
        "A.9",
        "large_hail",
        "Крупный град",
        "convective",
        "catalog_only",
        ("official_warning", "radar_hail_signature", "hail_size_observation"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "CAPE не считается прогнозом града или его диаметра.",
    ),
    HazardType(
        "A.10",
        "severe_blizzard",
        "Сильная метель",
        "snow",
        "catalog_only",
        ("wind_speed", "snowfall", "visibility", "duration"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Нужны совместные ветер, снег, видимость и продолжительность.",
    ),
    HazardType(
        "A.11",
        "severe_dust_storm",
        "Сильная пыльная или песчаная буря",
        "visibility",
        "catalog_only",
        ("wind_speed", "visibility", "duration", "bare_soil_state"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Одна скорость ветра не доказывает пыльную бурю.",
    ),
    HazardType(
        "A.12",
        "severe_fog",
        "Сильный туман или сильная мгла",
        "visibility",
        "catalog_only",
        ("visibility", "duration", "humidity", "aerosol_context"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "В базовом контуре нет проверенного прогноза видимости.",
    ),
    HazardType(
        "A.13",
        "severe_icing_deposition",
        "Сильное гололёдно-изморозевое отложение",
        "icing",
        "catalog_only",
        ("deposition_diameter", "precipitation_type", "surface_temperature"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Температура воздуха сама по себе не определяет диаметр отложения.",
    ),
    HazardType(
        "A.14",
        "severe_frost",
        "Сильный мороз",
        "temperature",
        "model_screening",
        ("minimum_air_temperature", "territorial_threshold"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Бот показывает холод, но не присваивает региональный статус ОЯ.",
    ),
    HazardType(
        "A.15",
        "severe_heat",
        "Сильная жара",
        "temperature",
        "model_screening",
        ("maximum_air_temperature", "territorial_threshold"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Бот показывает жару как screening, а не официальное ОЯ.",
    ),
    HazardType(
        "A.16",
        "anomalously_cold_weather",
        "Аномально холодная погода",
        "temperature",
        "catalog_only",
        ("daily_mean_temperature", "climate_normal", "duration"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Нужны однородная климатическая норма и непрерывный ряд.",
    ),
    HazardType(
        "A.17",
        "anomalously_hot_weather",
        "Аномально жаркая погода",
        "temperature",
        "catalog_only",
        ("daily_mean_temperature", "climate_normal", "duration"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Нужны однородная климатическая норма и непрерывный ряд.",
    ),
    HazardType(
        "A.18",
        "vegetation_frost",
        "Заморозок в период вегетации или уборки",
        "agro_temperature",
        "model_screening",
        ("minimum_air_temperature", "surface_temperature", "crop_phase"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Tmin на высоте 2 м остаётся ранним сигналом, а не температурой растения.",
    ),
    HazardType(
        "A.19",
        "extreme_fire_danger",
        "Чрезвычайная пожарная опасность",
        "fire",
        "catalog_only",
        ("nesterov_index", "precipitation_history", "official_fire_class"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Пожарный класс в базовом контуре не рассчитывается.",
    ),
    HazardType(
        "A.20",
        "snow_avalanche",
        "Сход снежных лавин",
        "snow",
        "catalog_only",
        ("official_warning", "snowpack", "slope", "avalanche_observation"),
        METEOROLOGICAL_HAZARD_SOURCE.key,
        "Точечный полевой бот не является лавинной службой.",
    ),
)


AGROMETEOROLOGICAL_HAZARDS: tuple[HazardType, ...] = (
    HazardType(
        "A.1.01",
        "agro_frost",
        "Заморозок",
        "agro_temperature",
        "model_screening",
        ("minimum_air_temperature", "surface_temperature", "crop_phase"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Требует подтверждённой культуры, стадии и факта повреждения.",
    ),
    HazardType(
        "A.1.02",
        "agro_anomalous_heat",
        "Аномально жаркая погода",
        "agro_temperature",
        "model_screening",
        ("daily_mean_temperature", "climate_normal", "duration", "crop_phase"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Текущий экран жары не является оценкой потерь урожая.",
    ),
    HazardType(
        "A.1.03",
        "dry_wind",
        "Суховей",
        "agro_temperature",
        "catalog_only",
        ("air_temperature", "relative_humidity", "wind_speed", "duration"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Нужен совместный расчёт температуры, влажности и ветра по культуре.",
    ),
    HazardType(
        "A.1.04",
        "soil_drought",
        "Засуха почвенная",
        "agro_moisture",
        "catalog_only",
        ("root_zone_available_water", "soil_layer", "duration", "crop_phase"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Осадки минус ET0 не являются запасом продуктивной влаги.",
    ),
    HazardType(
        "A.1.05",
        "atmospheric_drought",
        "Засуха атмосферная",
        "agro_temperature",
        "catalog_only",
        ("precipitation_deficit", "air_temperature", "humidity", "duration"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Короткий прогноз не заменяет длительный непрерывный ряд.",
    ),
    HazardType(
        "A.1.06",
        "drought_complex",
        "Комплекс засушливых явлений",
        "agro_moisture",
        "catalog_only",
        ("soil_drought", "atmospheric_drought", "dry_wind"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Комплекс не формируется без всех исходных составляющих.",
    ),
    HazardType(
        "A.1.07",
        "intense_rains",
        "Интенсивные дожди",
        "agro_moisture",
        "model_screening",
        ("precipitation_amount", "intensity", "duration", "crop_phase"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Модельные осадки дают только ранний сигнал для осмотра.",
    ),
    HazardType(
        "A.1.08",
        "anomalously_wet_weather",
        "Аномально влажная погода",
        "agro_moisture",
        "catalog_only",
        ("precipitation_vs_normal", "relative_humidity", "duration", "crop_phase"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Нужны климатическая норма и продолжительный непрерывный период.",
    ),
    HazardType(
        "A.1.09",
        "soil_waterlogging",
        "Переувлажнение почвы",
        "agro_moisture",
        "catalog_only",
        ("soil_moisture", "soil_consistency", "duration", "soil_texture"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Без почвенного наблюдения бот не объявляет поле переувлажнённым.",
    ),
    HazardType(
        "A.1.10",
        "crop_flooding",
        "Затопление посева",
        "agro_moisture",
        "catalog_only",
        ("flooded_area_fraction", "water_depth", "duration", "field_polygon"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Точечные осадки не определяют площадь затопленного поля.",
    ),
    HazardType(
        "A.1.11",
        "hail_damage",
        "Градобитие",
        "convective",
        "catalog_only",
        ("hail_observation", "damaged_plant_fraction", "damaged_area_fraction"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Требуется фактическое обследование повреждённых растений и площади.",
    ),
    HazardType(
        "A.1.12",
        "agro_strong_wind",
        "Сильный ветер",
        "agro_wind",
        "model_screening",
        ("maximum_wind_speed", "duration", "crop_phase", "crop_height"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Порыв модели не является универсальной моделью полегания.",
    ),
    HazardType(
        "A.1.13",
        "agro_hurricane_wind",
        "Ураганный ветер",
        "agro_wind",
        "model_screening",
        ("maximum_wind_speed", "crop_damage_observation"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Факт гибели растений подтверждается обследованием.",
    ),
    HazardType(
        "A.1.14",
        "agro_dust_storm",
        "Пыльная буря",
        "agro_wind",
        "catalog_only",
        ("wind_speed", "visibility", "duration", "soil_surface_state"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Нужны видимость, состояние поверхности и длительность.",
    ),
    HazardType(
        "A.2.01",
        "winterkill_field_crops",
        "Вымерзание полевых культур",
        "agro_winter",
        "catalog_only",
        ("soil_temperature_3cm", "air_temperature", "snow_depth", "crop_hardiness"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Нужны температура почвы требуемой глубины, снег и состояние посевов.",
    ),
    HazardType(
        "A.2.02",
        "winterkill_perennial_plantings",
        "Вымерзание многолетних насаждений",
        "agro_winter",
        "catalog_only",
        ("soil_temperature_20cm", "air_temperature", "snow_depth", "plant_hardiness"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Слой 0–7 см нельзя подставлять вместо температуры на глубине 20 см.",
    ),
    HazardType(
        "A.2.03",
        "damping_off",
        "Выпревание",
        "agro_winter",
        "catalog_only",
        ("snow_depth", "soil_freezing_depth", "soil_temperature_3cm", "duration"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Требуется многодекадный снежно-почвенный ряд.",
    ),
    HazardType(
        "A.2.04",
        "ice_crust",
        "Ледяная корка",
        "agro_winter",
        "catalog_only",
        ("ice_layer_thickness", "duration", "winter_crop_state"),
        AGROMETEOROLOGICAL_HAZARD_REFERENCE.key,
        "Факт и толщину корки подтверждают наблюдением на поле.",
    ),
)


PEST_MARKERS: tuple[PestMarker, ...] = (
    PestMarker(
        "air_daily_temperature",
        "Суточные Tmin и Tmax воздуха на высоте 2 м",
        "weather_driver",
        "implemented",
        True,
        "°C",
        "Температурный ряд завершённых местных суток и отдельного прогноза.",
        "Используется только моделями, для которых опубликован воздушный driver.",
    ),
    PestMarker(
        "soil_temperature_0_to_7cm",
        "Температура модельного слоя почвы 0–7 см",
        "weather_driver",
        "implemented",
        True,
        "°C",
        "Почасовой ECMWF/ERA5-Land ряд, агрегированный по местным суткам.",
        "Не считается датчиком на глубине семени и не заменяет другие слои.",
    ),
    PestMarker(
        "degree_day_accumulation",
        "Накопление градусо-суток",
        "calculation",
        "implemented",
        True,
        "°C·сут",
        "Суммирование только по непрерывному ряду завершённых суток.",
        "Метод и базовая температура задаются конкретной моделью вида.",
    ),
    PestMarker(
        "upper_temperature_cutoff",
        "Верхний температурный предел развития",
        "calculation",
        "implemented",
        True,
        "°C",
        "Ограничивает вклад температуры выше опубликованного верхнего порога.",
        "Не добавляется модели без первичного источника.",
    ),
    PestMarker(
        "field_observation_biofix",
        "Полевое наблюдение как точка отсчёта",
        "biofix",
        "implemented",
        False,
        "дата и тип находки",
        "Первая кладка, первая подтверждённая стадия или другое событие.",
        "Погода не может автоматически заменить фактическую находку.",
    ),
    PestMarker(
        "pheromone_trap_biofix",
        "Значимый улов в феромонной ловушке",
        "biofix",
        "implemented",
        False,
        "дата, вид и число особей",
        "Пороговый улов задаёт начало температурного отсчёта.",
        "Без ловушки и определения вида модель не запускается.",
    ),
    PestMarker(
        "calendar_biofix",
        "Опубликованное календарное начало",
        "biofix",
        "implemented",
        False,
        "календарная дата",
        "Автоматическая дата используется только когда она задана источником.",
        "Дата посева не подставляется вместо календарного biofix.",
    ),
    PestMarker(
        "continuous_completed_series",
        "Непрерывность завершённого температурного ряда",
        "quality",
        "implemented",
        True,
        "число суток и пропусков",
        "Каждые ожидаемые сутки должны иметь валидные Tmin и Tmax.",
        "При пропуске расчёт скрывается, а не заполняется нулём.",
    ),
    PestMarker(
        "forecast_separation",
        "Отделение прогноза от накопленного значения",
        "quality",
        "implemented",
        True,
        "тип строки и дата",
        "Будущие сутки используются только для следующего окна осмотра.",
        "Прогноз не включается в уже накопленную сумму.",
    ),
    PestMarker(
        "hourly_air_temperature",
        "Почасовая температура воздуха",
        "weather_driver",
        "candidate_unlinked",
        True,
        "°C, почасовая",
        "Нужна видам с почасовой или нелинейной реакцией на температуру.",
        "Не связана ни с одной культурой до появления точной модели.",
    ),
    PestMarker(
        "precipitation_amount_intensity_duration",
        "Сумма, интенсивность и продолжительность осадков",
        "weather_driver",
        "candidate_unlinked",
        True,
        "мм, мм/ч, ч",
        "Может влиять на выживаемость, смыв, выход и доступность хозяина.",
        "Общий признак «дождливо» не создаёт модель вредителя.",
    ),
    PestMarker(
        "rain_free_interval",
        "Продолжительность периода без дождя",
        "weather_driver",
        "candidate_unlinked",
        True,
        "ч или сут",
        "Кандидат для лёта, выхода и обследования отдельных видов.",
        "Не используется без видоспецифичного источника.",
    ),
    PestMarker(
        "relative_humidity_dewpoint_vpd",
        "Влажность, точка росы и дефицит давления водяного пара",
        "weather_driver",
        "candidate_unlinked",
        True,
        "%, °C, кПа",
        "Описывает влажностный режим воздуха без сведения его к одному числу.",
        "Порог должен быть опубликован для конкретного вида и стадии.",
    ),
    PestMarker(
        "leaf_wetness_duration",
        "Продолжительность увлажнения листа",
        "weather_driver",
        "candidate_unlinked",
        True,
        "ч",
        "Потенциальный фактор активности, выживания и взаимодействия с болезнями.",
        "Расчётная влажность воздуха не считается прямым датчиком листа.",
    ),
    PestMarker(
        "soil_moisture_waterlogging",
        "Влажность и переувлажнение почвы",
        "weather_driver",
        "candidate_unlinked",
        True,
        "м³/м³, % доступной влаги или наблюдение",
        "Кандидат для почвенных стадий, куколок и личинок.",
        "Осадки минус ET0 не заменяют влажность нужного слоя.",
    ),
    PestMarker(
        "wind_migration",
        "Скорость, направление и траектория переноса ветром",
        "weather_driver",
        "candidate_unlinked",
        True,
        "м/с, градусы, траектория",
        "Кандидат для мигрирующих бабочек, тлей и других переносимых видов.",
        "Точечный ветер без источника популяции не доказывает миграцию.",
    ),
    PestMarker(
        "snow_soil_freezing_winter_minimum",
        "Снег, промерзание и зимний минимум температуры",
        "weather_driver",
        "candidate_unlinked",
        True,
        "см, °C, продолжительность",
        "Кандидат для оценки перезимовки конкретных стадий.",
        "Нельзя переносить универсальную зимнюю выживаемость между видами.",
    ),
    PestMarker(
        "photoperiod",
        "Фотопериод",
        "weather_driver",
        "candidate_unlinked",
        True,
        "ч светлого времени",
        "Кандидат для диапаузы и сезонных переходов отдельных видов.",
        "Не включается без экспериментально подтверждённой реакции вида.",
    ),
    PestMarker(
        "crop_phenology",
        "Фактическая стадия культуры-хозяина",
        "context",
        "context_only",
        False,
        "наблюдаемая стадия",
        "Определяет доступность и уязвимость хозяина.",
        "Стадия подтверждается пользователем и не выводится из вредителя.",
    ),
    PestMarker(
        "host_condition",
        "Состояние и повреждённость растения-хозяина",
        "context",
        "context_only",
        False,
        "полевой учёт",
        "Нужен для отделения температурного развития от фактического ущерба.",
        "Без осмотра не формируется решение о мерах защиты.",
    ),
    PestMarker(
        "local_station_sensor_bias",
        "Сравнение модели с локальной станцией или датчиком",
        "quality",
        "context_only",
        False,
        "ошибка, смещение, глубина датчика",
        "Позволяет оценивать локальное систематическое отклонение температуры.",
        "Поправка не рассчитывается без накопленной пары модель–наблюдение.",
    ),
)

PEST_MARKERS_BY_KEY: dict[str, PestMarker] = {
    marker.key: marker for marker in PEST_MARKERS
}


def get_hazard_source(source_key: str) -> HazardSource:
    try:
        return HAZARD_SOURCES[source_key]
    except KeyError as exc:
        raise ValueError("Неизвестный источник каталога опасных явлений.") from exc


def get_pest_marker(marker_key: str) -> PestMarker:
    try:
        return PEST_MARKERS_BY_KEY[marker_key]
    except KeyError as exc:
        raise ValueError("Неизвестный маркер модели вредителя.") from exc


def pest_markers_by_status(status: PestMarkerStatus) -> tuple[PestMarker, ...]:
    return tuple(marker for marker in PEST_MARKERS if marker.status == status)


def validate_marker_catalog() -> None:
    hazard_codes: set[tuple[str, str]] = set()
    hazard_keys: set[str] = set()
    for hazard in (*METEOROLOGICAL_HAZARDS, *AGROMETEOROLOGICAL_HAZARDS):
        source = get_hazard_source(hazard.source_key)
        identity = (source.key, hazard.code)
        if identity in hazard_codes:
            raise RuntimeError(f"Повтор кода опасного явления: {identity}")
        if hazard.key in hazard_keys:
            raise RuntimeError(f"Повтор ключа опасного явления: {hazard.key}")
        if not hazard.screening_inputs:
            raise RuntimeError(f"Для {hazard.key} не перечислены входные маркеры")
        hazard_codes.add(identity)
        hazard_keys.add(hazard.key)

    marker_keys: set[str] = set()
    for marker in PEST_MARKERS:
        if marker.key in marker_keys:
            raise RuntimeError(f"Повтор ключа маркера вредителя: {marker.key}")
        if marker.status == "candidate_unlinked" and marker.role == "biofix":
            raise RuntimeError(
                f"Кандидат {marker.key} не должен объявляться готовым biofix"
            )
        marker_keys.add(marker.key)


validate_marker_catalog()
