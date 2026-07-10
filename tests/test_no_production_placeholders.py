from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_contains_no_synthetic_ml_training() -> None:
    forbidden = (
        "RandomForestClassifier",
        "synthetic_crop_data",
        "train_basic_model.py",
    )
    paths = list((ROOT / "src").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py"))
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in forbidden:
            assert marker not in text, f"{marker} in {path.relative_to(ROOT)}"


def test_critical_runtime_files_do_not_raise_not_implemented() -> None:
    paths = (
        ROOT / "src/bot/main.py",
        ROOT / "src/bot/scheduler.py",
        ROOT / "src/application/agro_report.py",
        ROOT / "src/api/open_meteo.py",
        ROOT / "src/agro/indices.py",
    )
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                if isinstance(node.exc.func, ast.Name):
                    assert node.exc.func.id != "NotImplementedError", path


def test_unimplemented_products_are_explicitly_disabled() -> None:
    matrix = (ROOT / "docs/PRODUCTION_CAPABILITIES.md").read_text(encoding="utf-8")
    assert "Прогноз урожайности | ❌ не реализован" in matrix
    assert "Синтетическая ML-модель | ❌ запрещена" in matrix
    assert "SPI | ❌ не рассчитывается" in matrix
