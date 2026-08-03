from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

PestCalculationMethod = Literal["daily_average"]
PestBiofixType = Literal["first_eggs"]
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
    biofix_type: PestBiofixType
    biofix_label: str
    lower_threshold_c: float
    upper_threshold_c: float | None
    calculation_method: PestCalculationMethod
    model_version: str
    source_title: str
    source_url: str
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
    biofix_type="first_eggs",
    biofix_label="первая найденная кладка яиц",
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


PEST_MODELS: dict[str, PestModel] = {
    COLORADO_POTATO_BEETLE.key: COLORADO_POTATO_BEETLE,
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
