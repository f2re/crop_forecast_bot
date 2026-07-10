from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"replacement marker not found in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, block: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if marker not in text:
        target.write_text(text.rstrip() + "\n\n" + block.strip() + "\n", encoding="utf-8")


def remove_path(path: str) -> None:
    target = ROOT / path
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists() or target.is_symlink():
        target.unlink()


replace_once(
    "src/agro/indices.py",
    "from src.agro.crop_catalog import CROPS, get_crop\n",
    "from src.agro.crop_catalog import CROPS\n",
)
replace_once(
    "src/agro/indices.py",
    '''                "level": "critical" if t_min <= FROST_CRITICAL_T else "warning",\n                "data_kind": "forecast",\n''',
    '''                "level": "critical" if t_min <= FROST_CRITICAL_T else "warning",\n                "crop_key": crop,\n                "phase": phase,\n                "elevation_m": elevation_m,\n                "data_kind": "forecast",\n''',
)
replace_once(
    "src/knowledge/llm_advisor.py",
    'return f"⚠️ Сервис консультаций временно недоступен. Попробуйте позже."',
    'return "⚠️ Сервис консультаций временно недоступен. Попробуйте позже."',
)

replace_once(
    "README.md",
    '''Перед commit:\n\n```bash\nruff check alembic config src tests\npython -m compileall -q alembic config src tests\nbash -n scripts/*.sh\nshellcheck -x scripts/deploy.sh scripts/update.sh scripts/rollback.sh \\\n  scripts/status.sh scripts/help.sh scripts/install-systemd.sh\npython -m pytest -q\n```''',
    '''Перед commit запускайте единый read-only gate:\n\n```bash\nbash scripts/verify-production.sh\n```\n\nLive smoke Open-Meteo выполняется отдельно и не входит в детерминированный CI:\n\n```bash\nbash scripts/verify-production.sh --live-provider 55.75 37.62\n```''',
)

plan = ROOT / "docs/DEVELOPMENT_PLAN.md"
plan_text = plan.read_text(encoding="utf-8")
audit_section = '''## Фактический аудит 2026-07-10\n\nСостояние проверено по production-entrypoint, графу импортов, GitHub Actions и полному локальному запуску проверок.\n\n- production уже переведён на `python -m src.bot.main`, aiogram 3.x, PostgreSQL/Alembic и Redis;\n- основной flow `поле → культура → сезон → отчёт` доступен, но сценарных restart-тестов FSM пока нет;\n- Open-Meteo скрыт за async port/DTO, однако общий lifecycle HTTP-сессии, rate limit и circuit breaker ещё не реализованы;\n- scientific/data-quality срез исправляет разделение источников, запрет фиктивного нуля ET₀, исключение прогноза из ГТК и forecast-only frost screening;\n- удалены сломанный верхнеуровневый legacy-entrypoint, Docker helper, файловый storage и недостижимые prototype-модули;\n- постоянный CI является read-only и проверяет полный Python-tree одной командой `scripts/verify-production.sh`;\n- unit suite не заменяет реальные PostgreSQL/Redis, clean-host и Telegram/FSM integration tests.\n\nРешение по релизу: **условный no-go** до завершения следующего P0-среза с реальными PostgreSQL/Redis, restart FSM и конкурентным scheduler.\n\n'''
if audit_section not in plan_text:
    plan_text = plan_text.replace("## Целевая архитектура\n", audit_section + "## Целевая архитектура\n", 1)
plan_text = plan_text.replace(
    "- [x] удаление telebot и глобальных user state dictionaries;",
    "- [x] удаление telebot, глобальных user state dictionaries и сломанных legacy-entrypoints;",
)
plan_text = plan_text.replace(
    "- [x] CI, unit tests и запрет контейнерных deployment-файлов.",
    "- [x] read-only CI, unit tests, full-tree lint и запрет legacy/Docker runtime-файлов.",
)
plan_text = plan_text.replace(
    "- [ ] missing fraction для окна ГТК;",
    "- [x] missing fraction для окна ГТК;",
)
old_next = '''## Ближайший следующий вертикальный срез\n\n1. Реальные PostgreSQL/Redis integration tests.\n2. FSM restart tests для создания поля и ввода даты.\n3. Field archive/delete с подтверждением и безопасным выбором нового active field.\n4. Notification local hour и quiet hours.\n5. Mocked Open-Meteo end-to-end contract tests.'''
new_next = '''## План следующих вертикальных срезов\n\n### P0 — persistence и конкурентная устойчивость\n\n1. Testcontainers для PostgreSQL и Redis; проверка реальных partial indexes, `SELECT FOR UPDATE`, Alembic head и Redis TTL/lease semantics.\n2. Сценарные aiogram-тесты: create-field и season-date до/после restart Redis FSM.\n3. Два scheduler-процесса: distributed lock, deduplication, падение после send и повторный запуск.\n4. Устранение race в `get_or_create_user` и создании active field/season через upsert либо обработку `IntegrityError`.\n\nКритерий: один и тот же callback/job при конкурентном выполнении даёт один устойчивый результат, а FSM продолжается после рестарта.\n\n### P1 — provider reliability\n\n1. Общая управляемая async HTTP-сессия с явным startup/shutdown.\n2. Timeout на каждый вызов, retry с jitter, rate limiter, circuit breaker и измеримый cache policy.\n3. Mocked end-to-end Open-Meteo tests: timeout, 429/5xx, повреждённый payload, partial history и controlled fallback.\n4. DTO наблюдений; затем отдельные adapters ERA5-Land, SoilGrids и спутниковых данных без смешивания provenance.\n\nКритерий: отказ provider не блокирует event loop и формирует отчёт только из доступных данных с явной деградацией качества.\n\n### P1 — Telegram UX и уведомления\n\n1. Idempotency middleware и защита повторных callback.\n2. Archive/delete поля с подтверждением и атомарным выбором нового active field.\n3. Back/cancel во всех ветках FSM.\n4. Локальный час уведомлений и quiet hours для каждого поля.\n\nКритерий: весь flow достижим из `/start`, обратим, идемпотентен и не теряет состояние.\n\n### P1/P2 — научная валидация и release engineering\n\n1. GDD: crop-specific upper cutoff, DST/leap/long-gap tests и независимая валидация фаз.\n2. ГТК: согласованный сезонный ряд и правила непрерывности вегетационного периода.\n3. Заморозки: источники чувствительности культура/фаза, surface temperature, terrain и ensemble uncertainty.\n4. Dependency profiles и `uv.lock`; clean-host Debian/Astra smoke, restore/rollback verification, structured logs и metrics.\n\nКритерий: формула или рекомендация публикуется только при документированном источнике, валидном периоде, единицах, uncertainty и тестах.'''
if old_next not in plan_text:
    raise RuntimeError("next-slice block not found in docs/DEVELOPMENT_PLAN.md")
plan.write_text(plan_text.replace(old_next, new_next, 1), encoding="utf-8")

replace_once(
    "docs/PRODUCTION_CAPABILITIES.md",
    "| ERA5-Land/CDS в Telegram flow | ❌ не подключён | legacy/experimental код не является функцией продукта |",
    "| ERA5-Land/CDS в Telegram flow | ❌ не подключён | prototype удалён; adapter должен быть реализован заново через provider port |",
)
replace_once(
    "docs/PRODUCTION_CAPABILITIES.md",
    "Удалённые синтетические prototype-файлы:\n- `scripts/train_basic_model.py`",
    "Удалены недостижимые synthetic/legacy runtime-файлы; их наличие больше не используется как имитация production-возможности.",
)

append_once(
    "tests/test_no_production_placeholders.py",
    "def test_legacy_runtime_and_unreachable_prototypes_are_removed",
    '''def test_legacy_runtime_and_unreachable_prototypes_are_removed() -> None:\n    forbidden_paths = (\n        "main.py",\n        "run_bot.py",\n        ".dockerignore",\n        "scripts/deploy_to_platform.sh",\n        "scripts/migrate_json_to_db.py",\n        "src/api/era5_ag.py",\n        "src/api/main.py",\n        "src/bot/rag_handler.py",\n        "src/bot/plotting.py",\n        "src/bot/simple_recommender.py",\n        "src/data",\n        "src/models",\n        "src/storage",\n        "FIXES_APPLIED.md",\n        "MIGRATION_TO_DATABASE.md",\n        "gemini.md",\n        ".windsurfrules",\n        "docs/index.md",\n        "docs/index.html",\n    )\n    for relative_path in forbidden_paths:\n        assert not (ROOT / relative_path).exists(), relative_path''',
)

verify = '''#!/usr/bin/env bash\nset -Eeuo pipefail\n\nPROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\ncd "${PROJECT_ROOT}"\n\nPYTHON="${PYTHON:-}"\nif [[ -z "${PYTHON}" ]]; then\n  if [[ -x .venv/bin/python ]]; then\n    PYTHON=.venv/bin/python\n  elif [[ -x /opt/crop-forecast-bot/current/.venv/bin/python ]]; then\n    PYTHON=/opt/crop-forecast-bot/current/.venv/bin/python\n  else\n    PYTHON=python3\n  fi\nfi\n\nlog() {\n  printf '[verify-production] %s\\n' "$*"\n}\n\nlog "Checking forbidden and legacy runtime artifacts"\nfor path in Dockerfile docker-compose.yml .env.docker.example .dockerignore main.py run_bot.py; do\n  test ! -e "${path}"\ndone\n\nlog "Compiling all Python modules"\n"${PYTHON}" -m compileall -q alembic config src tests\n\nlog "Running ruff over the full Python tree"\n"${PYTHON}" -m ruff check src config alembic tests\n\nlog "Running the complete test suite"\nPYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \\\n  "${PYTHON}" -m pytest -vv -s --maxfail=1 -p pytest_asyncio.plugin\n\nif command -v shellcheck >/dev/null 2>&1; then\n  log "Checking native Bash scripts"\n  bash -n scripts/*.sh\n  shellcheck -x \\\n    scripts/deploy.sh \\\n    scripts/update.sh \\\n    scripts/rollback.sh \\\n    scripts/status.sh \\\n    scripts/help.sh \\\n    scripts/install-systemd.sh \\\n    scripts/smoke-provider.sh \\\n    scripts/verify-production.sh\nfi\n\nlog "Checking Alembic heads"\n"${PYTHON}" -m alembic heads\n\nif [[ "${1:-}" == "--live-provider" ]]; then\n  log "Running live Open-Meteo contract smoke check"\n  bash scripts/smoke-provider.sh "${2:-55.75}" "${3:-37.62}" "${4:-}"\nfi\n\nlog "Verification completed"\n'''
verify_path = ROOT / "scripts/verify-production.sh"
verify_path.write_text(verify, encoding="utf-8")
verify_path.chmod(0o755)

ci = '''name: CI\n\non:\n  pull_request:\n  push:\n    branches: [main]\n\npermissions:\n  contents: read\n\njobs:\n  test:\n    runs-on: ubuntu-latest\n    timeout-minutes: 20\n    env:\n      PYTHONPATH: ${{ github.workspace }}\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: "3.11"\n          cache: pip\n\n      - name: Install validation tools\n        run: |\n          sudo apt-get update\n          sudo apt-get install -y --no-install-recommends shellcheck\n          python -m pip install --upgrade pip\n          pip install \\\n            pytest pytest-asyncio ruff alembic aiosqlite \\\n            pandas numpy python-dotenv \\\n            aiogram redis SQLAlchemy asyncpg APScheduler \\\n            openmeteo-requests requests-cache retry-requests\n\n      - name: Verify production tree\n        run: bash scripts/verify-production.sh\n'''
(ROOT / ".github/workflows/ci.yml").write_text(ci, encoding="utf-8")

for path in (
    ".dockerignore",
    "main.py",
    "sitecustomize.py",
    "scripts/deploy_to_platform.sh",
    "scripts/migrate_json_to_db.py",
    "docs/AUDIT_VALIDATION_GATE.md",
    "src/api/era5_ag.py",
    "src/api/main.py",
    "src/bot/plotting.py",
    "src/bot/rag_handler.py",
    "src/bot/simple_recommender.py",
    "src/data",
    "src/models",
    "src/storage",
    "FIXES_APPLIED.md",
    "MIGRATION_TO_DATABASE.md",
    "gemini.md",
    ".windsurfrules",
    "docs/index.md",
    "docs/index.html",
):
    remove_path(path)
