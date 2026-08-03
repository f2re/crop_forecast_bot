"""Weather-dependent candidates for forage crops."""
from __future__ import annotations

from .types import BiologicalRiskCandidate, candidate

FORAGE_CANDIDATES: tuple[BiologicalRiskCandidate, ...] = (
    candidate(
        "alfalfa_weevil",
        "Люцерновый долгоносик",
        "Hypera postica",
        "pest",
        ("alfalfa",),
        "published_contract",
        ("Tmin и Tmax воздуха", "градусо-сутки с базой 8,9 °C"),
        ("календарное начало", "фаза люцерны", "учёт личинок и повреждений"),
        "Окна выхода имаго, отрождения личинок и усиления обследований.",
        "NEWA and UC IPM Alfalfa Weevil Models",
        (
            "https://newa.cornell.edu/alfalfa-weevil",
            "https://ipm.ucanr.edu/weather/phenology-models-description/"
            "alfalfa-weevil/",
        ),
        "current_operational_tool",
        "Разные источники могут использовать разные методы накопления. "
        "Перед реализацией выбирается один версионированный договор.",
    ),
    candidate(
        "potato_leafhopper_alfalfa",
        "Картофельная цикадка на люцерне",
        "Empoasca fabae",
        "pest",
        ("alfalfa",),
        "published_contract",
        ("Tmin и Tmax воздуха", "нижний порог 11,4 °C", "верхний 30 °C"),
        ("первое полевое обнаружение", "сачковые учёты", "высота культуры"),
        "Температурное развитие поколения после подтверждённого обнаружения.",
        "UC IPM Phenology Model Database",
        (
            "https://ipm.ucanr.edu/weather/phenology-models-description/"
            "potato-leafhopper/",
        ),
        "published_model",
        "Мигрирующий вредитель: локальные градусо-сутки не предсказывают "
        "первичный прилёт и не заменяют сачковые учёты.",
    ),
    candidate(
        "alfalfa_anthracnose",
        "Антракноз люцерны",
        "Colletotrichum trifolii",
        "disease",
        ("alfalfa",),
        "weather_screening_only",
        ("тёплая дождливая погода", "осадки", "влажность полога"),
        ("восприимчивый сорт", "источник инокулюма", "симптомы"),
        "Напоминание обследовать стебли после тёплого дождливого периода.",
        "University of Minnesota Extension Alfalfa Anthracnose",
        ("https://extension.umn.edu/plant-diseases/anthracnose-alfalfa",),
        "current_guidance",
        "В источнике нет открытого количественного алгоритма инфекции; "
        "допустим только погодный экран.",
    ),
)
