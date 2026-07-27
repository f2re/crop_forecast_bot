from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_native_deploy_installs_only_mvp_system_packages() -> None:
    deploy = _read("scripts/deploy.sh")

    for required in (
        "python3-venv",
        "postgresql-client",
        "redis-server",
        "ca-certificates",
        "git",
    ):
        assert required in deploy
    for unnecessary in (
        "gdal-bin",
        "libgdal-dev",
        "build-essential",
        "python3-dev",
        "libpq-dev",
        "rsync",
        "curl",
    ):
        assert unnecessary not in deploy


def test_deploy_enables_green_main_updates_and_disables_heavy_features() -> None:
    deploy = _read("scripts/deploy.sh")

    assert "AUTO_UPDATE_ENABLED=true" in deploy
    assert "AUTO_UPDATE_REQUIRE_GREEN_CI=true" in deploy
    assert "CLIMATE_REFERENCE_ENABLED=false" in deploy
    assert "RAG_ENABLED=false" in deploy
    assert "INSTALL_RAG_PROFILE=0" in deploy
    assert "BLOCKING_IO_WORKERS=2" in deploy
    assert "RISK_HISTORY_RETENTION_DAYS=30" in deploy
    assert 'service_control enable --now "${UPDATE_TIMER_NAME}"' in deploy


def test_update_checks_remote_and_green_ci_before_clone() -> None:
    update = _read("scripts/update.sh")

    remote_check = update.index('remote_branch_sha "${BRANCH}"')
    release_gate = update.index("-m src.ops.release_gate")
    clone_release = update.index('create_release "${BRANCH}"')
    assert remote_check < release_gate < clone_release
    assert '[[ "${NEW_RELEASE_SHA}" != "${remote_sha}" ]]' in update
    assert "keeping ${old_sha:0:12}" in update


def test_dependency_environment_is_reused_until_requirements_change() -> None:
    common = _read("scripts/common.sh")

    assert "VENV_ROOT" in common
    assert "requirements_hash" in common
    assert "Reusing shared Python environment" in common
    assert 'ln -s "${shared_venv}" "${release}/.venv"' in common
    assert "prune_shared_venvs" in common
    assert 'KEEP_RELEASES="${KEEP_RELEASES:-2}"' in common
    assert 'KEEP_BACKUPS="${KEEP_BACKUPS:-3}"' in common


def test_update_timer_checks_main_frequently_without_busy_loop() -> None:
    timer = _read("deploy/systemd/crop-forecast-bot-update.timer")

    assert "OnCalendar=*:0/15" in timer
    assert "RandomizedDelaySec=90s" in timer
    assert "Persistent=true" in timer


def test_runtime_has_soft_resource_controls_without_hard_memory_kill() -> None:
    service = _read("deploy/systemd/crop-forecast-bot.service")

    assert "MALLOC_ARENA_MAX=2" in service
    assert "OPENBLAS_NUM_THREADS=1" in service
    assert "OMP_NUM_THREADS=1" in service
    assert "MemoryHigh=384M" in service
    assert "TasksMax=64" in service
    assert "MemoryMax=" not in service


def test_ci_runs_production_startup_smoke() -> None:
    workflow = _read(".github/workflows/ci.yml")

    assert "Production MVP startup smoke" in workflow
    assert "python -m alembic upgrade head" in workflow
    assert "python -m src.bot.main --startup-smoke" in workflow
    assert 'CLIMATE_REFERENCE_ENABLED: "false"' in workflow
