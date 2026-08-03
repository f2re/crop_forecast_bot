from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from src.domain.marker_catalog import get_pest_marker

PestCalculationMethod = Literal["daily_average", "single_sine_horizontal"]
PestBiofixType = Literal[
    "first_eggs",
    "significant_moth_catch",
    "calendar_jan1",
]
PestBiofixMode = Literal["user_observation", "calendar"]
PestTemperatureDriver = Literal["air_2m", "soil_0_to_7cm"]
PestNotificationKind = Literal["current_window", "approaching_window"]


@dataclass(frozen=True, slots=True)
class PestStage:
    key: str
    label: str
    start_dd_c: float
    end_dd_c: float | None
    scouting_action: str


@dataclass(frozen=True, slots=True)
class PestModel:
    key: str
    name_ru: str
    scientific_name: str
    crop_keys: tuple[str, ...]
    marker_keys: tuple[str, ...]
    biofix_type: PestBiofixType
    biofix_mode: PestBiofixMode
    biofix_label: str
    biofix_help: str
    temperature_driver: PestTemperatureDriver
    temperature_label: str
    lower_threshold_c: float
    upper_threshold_c: float | None
    calculation_method: PestCalculationMethod
    model_version: str
    source_title: str
    source_url: str
    supporting_source_urls: tuple[str, ...]
    validation_note: str
    stages: tuple[PestStage, ...]


@dataclass(frozen=True, slots=True)
class PestOutlook:
    available: bool
    status: str
    model: PestModel
    biofix_date: date
    accumulated_dd_c: float | None
    completed_days: int
    expected_days: int
    missing_days: int
    current_stage: PestStage | None
    next_stage: PestStage | None
    next_threshold_dd_c: float | None
    projected_crossing_date: date | None
    forecast_added_dd_c: float | None
    forecast_days: int
    period_end: date | None
    source_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class PestNotification:
    event_key: str
    kind: PestNotificationKind
    stage: PestStage
    expected_date: date | None


COLORADO_POTATO_BEETLE = PestModel(
    key="colorado_potato_beetle",
    name_ru="Колорадский жук",
    scientific_name="Leptinotarsa decemlineata",
    crop_keys=("potato",),
    marker_keys=(
        "air_daily_temperature",
        "degree_day_accumulation",
        "field_observation_biofix",
        "continuous_completed_series",
        "forecast_separation",
    ),
    biofix_type="first_eggs",
    biofix_mode="user_observation",
    biofix_label="первая найденная кладка яиц",
    biofix_help=(
        "Укажите дату первой кладки, которую действительно нашли на этом поле. "
        "Дата посадки картофеля не заменяет наблюдение вредителя."
    ),
    temperature_driver="air_2m",
    temperature_label="минимальная и максимальная температура воздуха на 2 м",
    lower_threshold_c=11.1,
    upper_threshold_c=None,
    calculation_method="daily_average",
    model_version="cpb-wi-2026-v1",
    source_title=(
        "University of Wisconsin Vegetable Entomology: Colorado Potato Beetle"
    ),
    source_url=(
        "https://vegento.russell.wisc.edu/pests/colorado-potato-beetle/"
    ),
    supporting_source_urls=(),
    validation_note=(
        "Пороговые суммы опубликованы для Верхнего Среднего Запада США. "
        "В боте они используются только как окно осмотра после подтверждённой "
        "кладки яиц и требуют проверки в местных условиях."
    ),
    stages=(
        PestStage(
            key="eggs",
            label="яйца; ожидается вылупление",
            start_dd_c=0.0,
            end_dd_c=120.0,
            scouting_action=(
                "Осмотрите нижнюю сторону листьев, особенно по краям поля, и "
                "отметьте число кладок."
            ),
        ),
        PestStage(
            key="larva_1",
            label="молодые личинки первого возраста",
            start_dd_c=120.0,
            end_dd_c=185.0,
            scouting_action=(
                "Ищите мелких красноватых личинок рядом с кладками и оцените "
                "начало повреждения листьев."
            ),
        ),
        PestStage(
            key="larva_2",
            label="личинки второго возраста",
            start_dd_c=185.0,
            end_dd_c=240.0,
            scouting_action=(
                "Повторите осмотр растений и отдельно запишите численность "
                "молодых личинок и долю повреждённой листовой поверхности."
            ),
        ),
        PestStage(
            key="larva_3",
            label="личинки третьего возраста",
            start_dd_c=240.0,
            end_dd_c=300.0,
            scouting_action=(
                "Проверьте распространение очагов и фактическую дефолиацию; "
                "не принимайте решение только по температурному расчёту."
            ),
        ),
        PestStage(
            key="larva_4",
            label="крупные личинки четвёртого возраста",
            start_dd_c=300.0,
            end_dd_c=400.0,
            scouting_action=(
                "Осмотрите поле без задержки: крупные личинки дают основную "
                "часть объедания ботвы. Сопоставьте факт с местным порогом вреда."
            ),
        ),
        PestStage(
            key="pupae",
            label="окукливание в почве",
            start_dd_c=400.0,
            end_dd_c=675.0,
            scouting_action=(
                "Продолжайте наблюдать за появлением нового поколения взрослых "
                "жуков; прямое наличие вредителя расчёт температуры не доказывает."
            ),
        ),
        PestStage(
            key="next_generation",
            label="возможен выход взрослых жуков следующего поколения",
            start_dd_c=675.0,
            end_dd_c=None,
            scouting_action=(
                "Возобновите осмотр взрослых жуков и новых кладок. Для нового "
                "цикла лучше отметить свежую первую кладку отдельной датой."
            ),
        ),
    ),
)


BLACK_CUTWORM = PestModel(
    key="black_cutworm",
    name_ru="Совка ипсилон (чёрная совка)",
    scientific_name="Agrotis ipsilon",
    crop_keys=("corn",),
    marker_keys=(
        "air_daily_temperature",
        "degree_day_accumulation",
        "pheromone_trap_biofix",
        "continuous_completed_series",
        "forecast_separation",
    ),
    biofix_type="significant_moth_catch",
    biofix_mode="user_observation",
    biofix_label="значимый улов бабочек в феромонной ловушке",
    biofix_help=(
        "Укажите дату, на которую в ловушке суммарно отмечено не менее восьми "
        "бабочек за две последовательные ночи. Без ловушки и идентификации "
        "вида расчёт не запускается."
    ),
    temperature_driver="air_2m",
    temperature_label="минимальная и максимальная температура воздуха на 2 м",
    lower_threshold_c=10.0,
    upper_threshold_c=None,
    calculation_method="daily_average",
    model_version="black-cutworm-mn-2026-v1",
    source_title="University of Minnesota Extension: Black cutworm in corn",
    source_url=(
        "https://extension.umn.edu/corn-pest-management/black-cutworm-corn"
    ),
    supporting_source_urls=(),
    validation_note=(
        "Модель создана для кукурузы и значимого улова в ловушке. Сам улов "
        "хорошо задаёт сроки развития, но может завышать риск повреждения поля. "
        "Сообщение используется только для выбора времени обследования."
    ),
    stages=(
        PestStage(
            key="eggs",
            label="яйцекладка и развитие яиц",
            start_dd_c=0.0,
            end_dd_c=50.0,
            scouting_action=(
                "Проверьте всходы и сорняки, но не считайте улов доказательством "
                "наличия личинок на поле."
            ),
        ),
        PestStage(
            key="larvae_1_3",
            label="личинки 1–3-го возрастов; питание листьями",
            start_dd_c=50.0,
            end_dd_c=173.3,
            scouting_action=(
                "Ищите небольшие отверстия и объедание листьев, осматривайте "
                "растения и поверхность почвы рядом с повреждениями."
            ),
        ),
        PestStage(
            key="larva_4",
            label="личинки 4-го возраста; начинается подгрызание растений",
            start_dd_c=173.3,
            end_dd_c=202.8,
            scouting_action=(
                "Начните целевой осмотр на увядающие и частично подрезанные "
                "растения, особенно в засорённых и пониженных местах."
            ),
        ),
        PestStage(
            key="larva_5",
            label="личинки 5-го возраста; основное окно подгрызания",
            start_dd_c=202.8,
            end_dd_c=239.4,
            scouting_action=(
                "Осмотрите поле без задержки и запишите долю повреждённых и "
                "подрезанных растений. Решение зависит от фактического учёта."
            ),
        ),
        PestStage(
            key="larvae_6_7",
            label="личинки 6–7-го возрастов; подгрызание ослабевает",
            start_dd_c=239.4,
            end_dd_c=356.1,
            scouting_action=(
                "Продолжайте учёт свежих повреждений; отделяйте старые следы от "
                "продолжающегося питания."
            ),
        ),
        PestStage(
            key="pupae",
            label="окукливание; питание прекращается",
            start_dd_c=356.1,
            end_dd_c=549.4,
            scouting_action=(
                "Проверьте, появляются ли новые повреждения. Температурный расчёт "
                "не заменяет осмотр и определение причины выпадения растений."
            ),
        ),
        PestStage(
            key="cycle_complete",
            label="опубликованное окно первого цикла завершено",
            start_dd_c=549.4,
            end_dd_c=None,
            scouting_action=(
                "Для нового цикла используйте свежий значимый улов в ловушке; "
                "не продолжайте старую точку отсчёта автоматически."
            ),
        ),
    ),
)


SEEDCORN_MAGGOT_SOIL = PestModel(
    key="seedcorn_maggot_soil",
    name_ru="Ростковая муха",
    scientific_name="Delia platura",
    crop_keys=("corn", "soy"),
    marker_keys=(
        "soil_temperature_0_to_7cm",
        "degree_day_accumulation",
        "upper_temperature_cutoff",
        "calendar_biofix",
        "continuous_completed_series",
        "forecast_separation",
    ),
    biofix_type="calendar_jan1",
    biofix_mode="calendar",
    biofix_label="календарное начало накопления 1 января",
    biofix_help=(
        "Дата устанавливается автоматически на 1 января текущего года. "
        "Пользовательская дата посадки не используется как начало развития "
        "перезимовавших куколок."
    ),
    temperature_driver="soil_0_to_7cm",
    temperature_label="температура модельного слоя почвы 0–7 см",
    lower_threshold_c=3.9,
    upper_threshold_c=29.0,
    calculation_method="single_sine_horizontal",
    model_version="seedcorn-maggot-soil-uc-2026-v1",
    source_title="UC IPM Phenology Model Database: Seedcorn Maggot",
    source_url=(
        "https://ipm.ucanr.edu/weather/phenology-models-description/"
        "seedcorn-maggot/"
    ),
    supporting_source_urls=(
        "https://agweather.cals.wisc.edu/thermal-models/scm",
        "https://extension.umn.edu/corn-pest-management/seedcorn-maggot",
    ),
    validation_note=(
        "Порог 206 °C·сут относится к 50% весеннего выхода взрослых мух и "
        "температуре почвы около 5,7 см в исследованиях Верхнего Среднего "
        "Запада США. Open-Meteo даёт модельный слой 0–7 см. Это окно осмотра "
        "для кукурузы и сои, а не оценка численности или ущерба."
    ),
    stages=(
        PestStage(
            key="overwintering_pupae",
            label="развитие перезимовавших куколок до весеннего выхода",
            start_dd_c=0.0,
            end_dd_c=206.0,
            scouting_action=(
                "Учитывайте историю поля, недавнюю заделку навоза или зелёной "
                "массы и состояние посевного слоя; одна температура не задаёт риск."
            ),
        ),
        PestStage(
            key="spring_emergence",
            label="достигнуто расчётное окно 50% весеннего выхода взрослых мух",
            start_dd_c=206.0,
            end_dd_c=None,
            scouting_action=(
                "Проверьте высокорисковые участки и всходы. Наличие повреждений "
                "подтверждают по семенам, проросткам и фактическим личинкам."
            ),
        ),
    ),
)


PEST_MODELS: dict[str, PestModel] = {
    model.key: model
    for model in (
        COLORADO_POTATO_BEETLE,
        BLACK_CUTWORM,
        SEEDCORN_MAGGOT_SOIL,
    )
}


def get_pest_model(pest_key: str) -> PestModel:
    try:
        return PEST_MODELS[pest_key]
    except KeyError as exc:
        raise ValueError("Неподдерживаемая модель вредителя.") from exc


def supported_pests_for_crop(crop_key: str) -> tuple[PestModel, ...]:
    return tuple(
        model for model in PEST_MODELS.values() if crop_key in model.crop_keys
    )


def validate_pest_for_crop(pest_key: str, crop_key: str) -> PestModel:
    model = get_pest_model(pest_key)
    if crop_key not in model.crop_keys:
        raise ValueError("Эта модель не применяется к выбранной культуре.")
    return model


def automatic_biofix_date(model: PestModel, today: date) -> date | None:
    if model.biofix_type == "calendar_jan1":
        return date(today.year, 1, 1)
    return None


def stage_for_accumulation(model: PestModel, accumulated_dd_c: float) -> PestStage:
    value = max(0.0, accumulated_dd_c)
    for stage in model.stages:
        if stage.end_dd_c is None or value < stage.end_dd_c:
            return stage
    return model.stages[-1]


def next_stage(model: PestModel, current: PestStage) -> PestStage | None:
    for index, stage in enumerate(model.stages):
        if stage.key == current.key:
            return model.stages[index + 1] if index + 1 < len(model.stages) else None
    raise ValueError("Стадия не входит в модель вредителя.")


def validate_pest_model_markers() -> None:
    required_driver = {
        "air_2m": "air_daily_temperature",
        "soil_0_to_7cm": "soil_temperature_0_to_7cm",
    }
    required_biofix = {
        "first_eggs": "field_observation_biofix",
        "significant_moth_catch": "pheromone_trap_biofix",
        "calendar_jan1": "calendar_biofix",
    }

    for model in PEST_MODELS.values():
        if not model.marker_keys:
            raise RuntimeError(
                f"Модель {model.key} не имеет проверяемых погодных маркеров."
            )
        markers = tuple(get_pest_marker(key) for key in model.marker_keys)
        forbidden = [
            marker.key for marker in markers if marker.status == "candidate_unlinked"
        ]
        if forbidden:
            raise RuntimeError(
                f"Модель {model.key} связана с недопущенными кандидатами: "
                + ", ".join(forbidden)
            )
        weather_drivers = [
            marker
            for marker in markers
            if marker.role == "weather_driver" and marker.status == "implemented"
        ]
        if not weather_drivers:
            raise RuntimeError(
                f"Модель {model.key} не имеет реализованного погодного driver."
            )
        expected_driver = required_driver[model.temperature_driver]
        if expected_driver not in model.marker_keys:
            raise RuntimeError(
                f"Модель {model.key} не объявляет driver {expected_driver}."
            )
        expected_biofix = required_biofix[model.biofix_type]
        if expected_biofix not in model.marker_keys:
            raise RuntimeError(
                f"Модель {model.key} не объявляет biofix {expected_biofix}."
            )
        if "degree_day_accumulation" not in model.marker_keys:
            raise RuntimeError(
                f"Модель {model.key} не объявляет температурное накопление."
            )
        if model.upper_threshold_c is not None and (
            "upper_temperature_cutoff" not in model.marker_keys
        ):
            raise RuntimeError(
                f"Модель {model.key} не объявляет верхний температурный предел."
            )


validate_pest_model_markers()
