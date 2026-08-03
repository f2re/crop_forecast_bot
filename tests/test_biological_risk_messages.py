from __future__ import annotations

from src.agro.crop_catalog import CROPS
from src.bot.biological_risk_messages import format_crop_biological_risks


def test_wheat_message_separates_diseases_pests_and_readiness() -> None:
    text = format_crop_biological_risks("wheat")

    assert "Фузариоз колоса" in text
    assert "Пшеничный комарик" in text
    assert "Жёлтая ржавчина" in text
    assert "🦠 <b>Болезни</b>" in text
    assert "🐛 <b>Вредители</b>" in text
    assert "не диагноз" in text
    assert "не команда на обработку" in text


def test_evidence_gap_does_not_claim_that_crop_has_no_pests() -> None:
    text = format_crop_biological_risks("millet")

    assert "Проверяемая погодная модель пока не найдена" in text
    assert "Это не означает, что у культуры нет болезней или вредителей" in text
    assert "Модели сорго" in text


def test_all_crop_messages_fit_telegram_limit() -> None:
    for crop_key in CROPS:
        text = format_crop_biological_risks(crop_key)
        assert 0 < len(text) < 4096, crop_key


def test_onion_message_discloses_multiple_contract_levels() -> None:
    text = format_crop_biological_risks("onion")

    assert "Ботритиоз листьев лука" in text
    assert "Пероноспороз лука" in text
    assert "Луковая муха" in text
    assert "Табачный трипс на зелёном луке" in text
    assert "действующий внешний инструмент" in text
    assert "формализованная опубликованная модель" in text
