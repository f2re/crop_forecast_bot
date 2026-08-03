"""Weather-dependent candidates for corn, rice, oilseeds and soybean."""
from __future__ import annotations

from .types import BiologicalRiskCandidate, candidate

FIELD_CROP_CANDIDATES: tuple[BiologicalRiskCandidate, ...] = (
    candidate(
        "corn_tar_spot",
        "Тар-спот кукурузы",
        "Phyllachora maydis",
        "disease",
        ("corn", "corn_silage"),
        "operational_external_model",
        ("локальная погода", "влажность", "температура"),
        ("фаза культуры", "региональное присутствие болезни"),
        "Суточный и семисуточный риск по валидированной внешней модели.",
        "Crop Protection Network Crop Risk Tool",
        (
            "https://cropprotectionnetwork.org/news/"
            "fungicide-decision-making-tools-and-resources",
        ),
        "current_operational_tool",
        "Нужен официальный алгоритм или API; для силосной кукурузы "
        "практические решения должны оставаться отдельными.",
    ),
    candidate(
        "corn_gray_leaf_spot",
        "Серая пятнистость листьев кукурузы",
        "Cercospora zeae-maydis and Cercospora zeina",
        "disease",
        ("corn", "corn_silage"),
        "operational_external_model",
        ("локальная погода", "температура", "влажность"),
        ("фаза культуры", "остатки кукурузы", "восприимчивость гибрида"),
        "Суточный и семисуточный риск по внешней модели.",
        "Crop Protection Network Crop Risk Tool",
        (
            "https://cropprotectionnetwork.org/news/"
            "fungicide-decision-making-tools-and-resources",
        ),
        "current_operational_tool",
        "Нужно получить воспроизводимый договор модели и проверить его "
        "для целевого региона.",
    ),
    candidate(
        "corn_gibberella_ear_rot",
        "Фузариоз початка",
        "Fusarium graminearum",
        "disease",
        ("corn", "corn_silage"),
        "operational_external_model",
        ("температура", "влажность", "осадки"),
        ("выброс рылец и цветение", "повреждение початков", "история региона"),
        "Погодное окно риска фузариоза початка без заявления о микотоксинах.",
        "Crop Protection Network Crop Risk Tool",
        (
            "https://cropprotectionnetwork.org/news/"
            "fungicide-decision-making-tools-and-resources",
        ),
        "current_operational_tool",
        "Вероятность микотоксинов нельзя переносить без точного договора, "
        "отбора проб и лабораторного анализа.",
    ),
    candidate(
        "western_bean_cutworm",
        "Западная совка бобовая",
        "Striacosta albicosta",
        "pest",
        ("corn", "corn_silage"),
        "published_contract",
        ("Tmin и Tmax воздуха", "градусо-сутки с базой 3,3 °C"),
        ("отсчёт с 1 марта", "феромонные ловушки", "фаза", "учёт кладок"),
        "Процент завершения лёта и срок усиления обследований.",
        "NEWA Western Bean Cutworm Flight Forecast",
        ("https://newa.cornell.edu/western-bean-cutworm",),
        "current_operational_tool",
        "Температурный расчёт задаёт сроки лёта, но риск подтверждают "
        "ловушки, кладки и фаза культуры.",
    ),
    candidate(
        "rice_blast",
        "Пирикуляриоз риса",
        "Magnaporthe oryzae",
        "disease",
        ("rice",),
        "regional_signal_required",
        ("температура", "длительное увлажнение", "роса и осадки"),
        ("наличие спор", "восприимчивый сорт", "фаза", "азотный фон"),
        "Период благоприятной инфекции при подтверждённом источнике патогена.",
        "IRRI Rice Knowledge Bank",
        (
            "https://www.knowledgebank.irri.org/training/fact-sheets/"
            "pest-management/diseases/item/blast-leaf-collar",
        ),
        "current_guidance",
        "Локальная погода не доказывает заражение без наличия патогена.",
    ),
    candidate(
        "rice_bacterial_blight",
        "Бактериальный ожог риса",
        "Xanthomonas oryzae pv. oryzae",
        "disease",
        ("rice",),
        "weather_screening_only",
        ("температура", "высокая влажность", "ливни", "сильный ветер"),
        ("заражённые остатки или сорняки", "повреждение листьев", "симптомы"),
        "Напоминание об обследовании после тёплой влажной и ветреной погоды.",
        "IRRI Rice Knowledge Bank",
        (
            "https://www.knowledgebank.irri.org/training/fact-sheets/"
            "pest-management/diseases/item/bacterial-blight",
        ),
        "current_guidance",
        "Без источника бактерии и симптомов допустим только погодный экран.",
    ),
    candidate(
        "rice_sheath_blight",
        "Ризоктониоз риса",
        "Rhizoctonia solani",
        "disease",
        ("rice",),
        "weather_screening_only",
        ("температура", "влажность в пологе", "осадки"),
        ("сомкнутый густой полог", "наличие склероциев", "фаза культуры"),
        "Период благоприятной погоды для обследования влагалищ листьев.",
        "IRRI Rice Knowledge Bank",
        (
            "https://www.knowledgebank.irri.org/training/fact-sheets/"
            "pest-management/diseases/item/sheath-blight",
        ),
        "current_guidance",
        "Микроклимат полога может заметно отличаться от сеточной модели.",
    ),
    candidate(
        "rice_false_smut",
        "Ложная головня риса",
        "Ustilaginoidea virens",
        "disease",
        ("rice",),
        "weather_screening_only",
        ("температура", "относительная влажность", "осадки"),
        ("цветение", "наличие патогена", "полевые симптомы"),
        "Период благоприятных условий во время цветения.",
        "IRRI Rice Knowledge Bank",
        (
            "https://www.knowledgebank.irri.org/training/fact-sheets/"
            "pest-management/diseases/item/false-smut",
        ),
        "current_guidance",
        "Допустим только сигнал благоприятности; болезнь подтверждается осмотром.",
    ),
    candidate(
        "sunflower_stem_weevil",
        "Подсолнечниковый стеблевой долгоносик",
        "Cylindrocopturus adspersus",
        "pest",
        ("sunflower",),
        "published_contract",
        ("Tmin и Tmax воздуха", "нижний порог 5 °C", "верхний 32 °C"),
        ("отсчёт с 1 января", "проверка имаго на поле"),
        "Начало и проценты весеннего выхода имаго.",
        "UC IPM Phenology Model Database",
        (
            "https://ipm.ucanr.edu/weather/phenology-models-description/"
            "sunflower-stem-weevil/",
        ),
        "published_model",
        "Модель Северных Великих равнин требует проверки минимум один сезон "
        "в целевом регионе.",
    ),
    candidate(
        "sunflower_beetle",
        "Подсолнечниковый листоед",
        "Zygogramma exclamationis",
        "pest",
        ("sunflower",),
        "published_contract",
        ("Tmin и Tmax воздуха", "нижний порог 0 °C", "верхний 32 °C"),
        ("отсчёт с 1 марта", "полевой учёт имаго и личинок"),
        "Первый и 50-процентный выход имаго.",
        "UC IPM Phenology Model Database",
        (
            "https://ipm.ucanr.edu/weather/phenology-models-description/"
            "sunflower-beetle/",
        ),
        "published_model",
        "Модель получена в Северной Дакоте; сроки не заменяют учёт.",
    ),
    candidate(
        "sunflower_moth",
        "Подсолнечниковая огнёвка",
        "Homoeosoma electellum",
        "pest",
        ("sunflower",),
        "published_contract",
        ("Tmin и Tmax воздуха", "нижний порог 13,3 °C"),
        ("отсчёт с 1 января", "феромонная ловушка", "начало цветения"),
        "Ожидаемые пики первого и второго лёта.",
        "UC IPM Phenology Model Database",
        (
            "https://ipm.ucanr.edu/weather/phenology-models-description/"
            "sunflower-moth/",
        ),
        "published_model",
        "Калибровка выполнена в Северной Калифорнии; связь с цветением "
        "и ловушками обязательна.",
    ),
    candidate(
        "rapeseed_sclerotinia_stem_rot",
        "Склеротиниоз рапса",
        "Sclerotinia sclerotiorum",
        "disease",
        ("rapeseed",),
        "weather_screening_only",
        ("влажность не ниже 80 %", "длительность влажности", "осадки", "температура"),
        ("20–50 % цветения", "влажный полог", "патоген или история поля"),
        "Период благоприятной погоды для проверки апотециев и полога.",
        "Canola Council of Canada Sclerotinia Risk Guidance",
        (
            "https://www.canolacouncil.org/canola-watch/fundamentals/"
            "factors-in-the-sclerotinia-spray-decision/",
        ),
        "current_guidance",
        "Метеостанция не измеряет влажность внутри полога; наличие спор "
        "и стадия цветения обязательны.",
    ),
    candidate(
        "bertha_armyworm",
        "Совка берта",
        "Mamestra configurata",
        "pest",
        ("rapeseed",),
        "published_contract",
        ("Tmin и Tmax воздуха", "градусо-сутки с базой 7 °C"),
        ("феромонные ловушки", "региональные уловы", "учёт личинок"),
        "Окно выхода имаго и начала работы ловушек.",
        "Canola Council of Canada Bertha Armyworm Guidance",
        (
            "https://www.canolacouncil.org/canola-watch/2014/06/25/"
            "map-of-the-week-8/",
            "https://www.canolacouncil.org/canola-watch/2018/06/13/"
            "map-of-the-week-bertha-armyworm/",
        ),
        "current_guidance",
        "Ранний выход не означает вспышку; риск определяется уловами "
        "и фактической численностью личинок.",
    ),
    candidate(
        "flax_pasmo",
        "Пасмо льна",
        "Septoria linicola",
        "disease",
        ("flax",),
        "weather_screening_only",
        ("продолжительная влажная погода", "температура", "влажность полога"),
        ("заражённые остатки или семена", "поздняя фаза", "симптомы"),
        "Напоминание об обследовании после длительного влажного периода.",
        "Manitoba Agriculture Pasmo in Flax",
        (
            "https://www.gov.mb.ca/agriculture/crops/plant-diseases/"
            "print%2Cpasmo-in-flax.html",
        ),
        "current_guidance",
        "В источнике нет воспроизводимого численного алгоритма инфекции.",
    ),
    candidate(
        "soy_white_mold",
        "Белая гниль сои",
        "Sclerotinia sclerotiorum",
        "disease",
        ("soy",),
        "operational_external_model",
        ("30-дневные температуры", "ветер", "локальная погода"),
        ("цветение", "смыкание полога", "ширина междурядий", "орошение"),
        "Вероятность благоприятных условий по внешней модели.",
        "Crop Protection Network and NEWA White Mold Tools",
        (
            "https://cropprotectionnetwork.org/news/"
            "fungicide-decision-making-tools-and-resources",
            "https://newa.cornell.edu/white-mold-in-beans",
        ),
        "current_operational_tool",
        "Модель требует параметров поля и региональной проверки; вывод "
        "подтверждается обследованием.",
    ),
    candidate(
        "soy_frogeye_leaf_spot",
        "Церкоспороз сои",
        "Cercospora sojina",
        "disease",
        ("soy",),
        "operational_external_model",
        ("локальная погода", "температура", "влажность"),
        ("фаза культуры", "восприимчивость сорта", "история поля"),
        "Суточный и семисуточный риск по внешней модели.",
        "Crop Protection Network Crop Risk Tool",
        (
            "https://cropprotectionnetwork.org/news/"
            "fungicide-decision-making-tools-and-resources",
        ),
        "current_operational_tool",
        "До интеграции нужен официальный алгоритм или API и независимая "
        "региональная проверка.",
    ),
)
