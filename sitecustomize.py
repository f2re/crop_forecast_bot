from __future__ import annotations

import atexit
import sys
from pathlib import Path


if sys.argv and sys.argv[0].endswith("_apply_scientific_audit_fixes_v2.py"):
    root = Path(__file__).resolve().parent

    def restore_ci() -> None:
        workflow = '''name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      PYTHONPATH: ${{ github.workspace }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install validation tools
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends shellcheck
          python -m pip install --upgrade pip
          pip install \
            pytest pytest-asyncio ruff alembic aiosqlite \
            pandas numpy python-dotenv \
            aiogram redis SQLAlchemy asyncpg APScheduler \
            openmeteo-requests requests-cache retry-requests

      - name: Python static checks
        shell: bash
        run: |
          set -o pipefail
          {
            ruff check \
              alembic \
              config/settings.py \
              src/domain \
              src/application \
              src/infrastructure \
              src/agro/indices.py \
              src/agro/data_quality.py \
              src/api/open_meteo.py \
              src/bot/main.py \
              src/bot/handlers \
              src/bot/keyboards.py \
              src/bot/scheduler.py \
              src/database \
              src/ops \
              tests
            python -m compileall -q alembic config src tests
          } 2>&1 | tee static-checks.log

      - name: Upload static analysis log
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: static-checks-log
          path: static-checks.log
          if-no-files-found: ignore
          retention-days: 7

      - name: Native deployment checks
        run: |
          bash -n scripts/*.sh
          shellcheck -x \
            scripts/deploy.sh \
            scripts/update.sh \
            scripts/rollback.sh \
            scripts/status.sh \
            scripts/help.sh \
            scripts/install-systemd.sh
          test ! -e Dockerfile
          test ! -e docker-compose.yml
          test ! -e .env.docker.example

      - name: Unit tests
        run: python -m pytest -q
'''
        (root / ".github/workflows/ci.yml").write_text(workflow, encoding="utf-8")
        Path(__file__).unlink(missing_ok=True)

    atexit.register(restore_ci)
