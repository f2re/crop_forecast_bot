"""Weather-dependent disease and pest candidates for grain crops."""
from __future__ import annotations

from .types import BiologicalRiskCandidate, candidate

GRAIN_CANDIDATES: tuple[BiologicalRiskCandidate, ...] = (
    candidate(
        "wheat_fusarium_head_blight",
        "Фузариоз колоса",
        "Fusarium graminearum species complex",
        "disease",
        ("wheat",),
        "operational_external_model",
        ("температура", "относительная влажность", "осадки или увлажнение"),
        ("колошение и цветение", "история болезни или источник инокулюма"),
        "Окно повышенного риска инфекции в восприимчивой фазе.",
        "Crop Protection Network Crop Risk Tool",
        (
            "https://cropprotectionnetwork.org/news/"
            "fungicide-decision-making-tools-and-resources",
        ),
        "current_operational_tool",
        "Нужен версионированный алгоритм или официальный API и проверка "
        "по регионам и годам.",
    ),
    candidate(
        "wheat_midge",
        "Пшеничный комарик",
        "Sitodiplosis mosellana",
        "pest",
        ("wheat",),
        "published_contract",
        ("Tmin и Tmax воздуха", "градусо-сутки с базой 4,4 °C"),
        ("дата посева", "колошение–начало цветения", "вечерний полевой учёт"),
        "Процент ожидаемого выхода самок и срок начала обследования.",
        "NDSU Field Guide to Sustainable Production of High-quality Durum Wheat",
        (
            "https://www.ndsu.edu/agriculture/extension/publications/"
            "field-guide-sustainable-production-high-quality-durum-wheat-"
            "north-dakota",
            "https://www.ndsu.edu/agriculture/ag-hub/wheat-midge-risk-maps",
        ),
        "current_guidance",
        "Пороги 1300/1475/1600 DD40°F относятся к Северной Дакоте; "
        "наличие и численность подтверждаются обследованием.",
    ),
    candidate(
        "cereal_leaf_beetle",
        "Пьявица красногрудая",
        "Oulema melanopus",
        "pest",
        ("wheat", "barley", "oat", "rye"),
        "published_contract",
        ("Tmin и Tmax воздуха", "градусо-сутки с базой 7,0 °C"),
        ("отсчёт с 1 января", "фаза культуры", "число яиц и личинок"),
        "Окна активности имаго, яйцекладки и начала отрождения личинок.",
        "NDSU Cereal Leaf Beetle IPM Guide",
        (
            "https://www.ndsu.edu/agriculture/extension/publications/"
            "cereal-leaf-beetle-oulema-melanopus-l-coleoptera-chrysomelidae",
        ),
        "current_guidance",
        "Модель задаёт сроки обследования, а порог решения зависит от фазы "
        "и фактического числа яиц и личинок.",
    ),
    candidate(
        "wheat_stripe_rust",
        "Жёлтая ржавчина пшеницы",
        "Puccinia striiformis f. sp. tritici",
        "disease",
        ("wheat",),
        "regional_signal_required",
        ("температура", "свободная вода на листьях", "ветер"),
        ("подтверждённый региональный очаг", "восприимчивый сорт", "фаза"),
        "Период благоприятной инфекции после подтверждения источника спор.",
        "USDA ARS Cereal Disease Laboratory",
        (
            "https://www.ars.usda.gov/midwest-area/stpaul/"
            "cereal-disease-lab/docs/cereal-rusts/wheat-stripe-rust/",
        ),
        "current_guidance",
        "Погода без данных об очаге и переносе спор не является прогнозом "
        "появления ржавчины.",
    ),
    candidate(
        "small_grain_bacterial_leaf_streak",
        "Бактериальная полосатость листьев",
        "Xanthomonas translucens",
        "disease",
        ("wheat", "barley", "oat", "triticale"),
        "weather_screening_only",
        ("тёплая влажная погода", "осадки", "ветер и град"),
        ("заражённые семена или остатки", "повреждение листьев", "симптомы"),
        "Напоминание об обследовании после благоприятной погоды и повреждений.",
        "University of Minnesota Extension",
        (
            "https://extension.umn.edu/small-grains-pest-management/"
            "bacterial-leaf-streak-and-black-chaff-small-grains",
        ),
        "current_guidance",
        "Заболевание очаговое и спорадическое; по метеоданным нельзя "
        "утверждать, что заражение произошло.",
    ),
    candidate(
        "barley_fusarium_head_blight",
        "Фузариоз колоса ячменя",
        "Fusarium spp.",
        "disease",
        ("barley",),
        "weather_screening_only",
        ("температура", "осадки", "высокая влажность"),
        ("выход колоса", "растительные остатки или другой источник инокулюма"),
        "Период погоды, благоприятной для обследования колоса.",
        "University of Minnesota Extension",
        (
            "https://extension.umn.edu/small-grains-crop-and-variety-selection/"
            "winter-barley-emerging-crop",
        ),
        "current_guidance",
        "Не найден отдельный открытый валидированный количественный договор "
        "риска для ячменя.",
    ),
    candidate(
        "barley_corn_leaf_aphid",
        "Обыкновенная злаковая тля",
        "Rhopalosiphum maidis",
        "pest",
        ("barley",),
        "published_contract",
        ("Tmin и Tmax воздуха", "нижний порог 6,1 °C", "верхний 26,3 °C"),
        ("фактическое обнаружение тли", "учёт численности"),
        "Температурное развитие поколения после полевого обнаружения.",
        "UC IPM Phenology Model Database",
        (
            "https://ipm.ucanr.edu/weather/phenology-models-description/"
            "corn-leaf-aphid/",
        ),
        "published_model",
        "Модель получена для ячменя, но не заменяет учёт заселённости и "
        "требует местной проверки.",
    ),
    candidate(
        "oat_crown_rust",
        "Корончатая ржавчина овса",
        "Puccinia coronata f. sp. avenae",
        "disease",
        ("oat",),
        "regional_signal_required",
        ("температура", "роса или свободная вода", "ветер"),
        ("региональный источник спор", "восприимчивый сорт", "фаза культуры"),
        "Окно благоприятной инфекции при подтверждённом переносе спор.",
        "USDA ARS Cereal Disease Laboratory",
        (
            "https://www.ars.usda.gov/midwest-area/stpaul/"
            "cereal-disease-lab/docs/cereal-rusts/oat-crown-rust/",
        ),
        "current_guidance",
        "Споры переносятся на большие расстояния; одной локальной погоды "
        "недостаточно.",
    ),
    candidate(
        "sorghum_anthracnose",
        "Антракноз сорго",
        "Colletotrichum sublineola",
        "disease",
        ("sorghum",),
        "weather_screening_only",
        ("тёплая погода", "дожди", "влажность листьев"),
        ("источник инокулюма", "восприимчивый гибрид", "период после цветения"),
        "Период благоприятной погоды для обследования.",
        "Alabama Cooperative Extension System Sorghum Diseases",
        ("https://ssl.acesag.auburn.edu/anr/crops/smallgrains/sorghumdiseases.php",),
        "current_guidance",
        "Руководство описывает условия, но не даёт валидированный численный "
        "алгоритм риска.",
    ),
    candidate(
        "sorghum_fusarium_head_mold",
        "Фузариозная плесень метёлки",
        "Fusarium spp.",
        "disease",
        ("sorghum",),
        "weather_screening_only",
        ("высокая влажность", "жаркая погода", "осадки"),
        ("цветение и налив зерна", "источник инокулюма"),
        "Напоминание осмотреть метёлки после благоприятного периода.",
        "Alabama Cooperative Extension System Sorghum Diseases",
        ("https://ssl.acesag.auburn.edu/anr/crops/smallgrains/sorghumdiseases.php",),
        "current_guidance",
        "Погода показывает только благоприятность, а не факт заражения или "
        "загрязнения микотоксинами.",
    ),
    candidate(
        "sorghum_charcoal_rot",
        "Угольная гниль сорго",
        "Macrophomina phaseolina",
        "disease",
        ("sorghum",),
        "weather_screening_only",
        ("жара", "длительный дефицит влаги"),
        ("наличие патогена", "стресс культуры", "фаза налива"),
        "Сигнал о погоде, усиливающей риск проявления болезни.",
        "Alabama Cooperative Extension System Sorghum Diseases",
        ("https://ssl.acesag.auburn.edu/anr/crops/smallgrains/sorghumdiseases.php",),
        "current_guidance",
        "Это стрессовый фон, а не диагноз; нужны осмотр стебля и история поля.",
    ),
)
