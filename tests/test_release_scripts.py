from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNITS = (
    "crop-forecast-bot.service",
    "crop-forecast-bot-update.service",
    "crop-forecast-bot-update.timer",
)


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _release(root: Path, name: str, marker: str) -> Path:
    release = root / name
    unit_dir = release / "deploy" / "systemd"
    unit_dir.mkdir(parents=True)
    for unit in UNITS:
        (unit_dir / unit).write_text(
            "\n".join(
                [
                    "[Unit]",
                    f"Description={marker} @APP_USER@",
                    "[Service]",
                    "Environment=HOME=@STATE_ROOT@",
                    "Environment=XDG_CACHE_HOME=@CACHE_ROOT@",
                    "WorkingDirectory=@CURRENT_LINK@",
                    "[Install]",
                    "WantedBy=multi-user.target",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    _write_executable(release / ".venv" / "bin" / "python", "#!/bin/sh\nexit 0\n")
    return release


def _base_env(tmp_path: Path) -> dict[str, str]:
    fake_systemctl = tmp_path / "bin" / "systemctl"
    fake_journalctl = tmp_path / "bin" / "journalctl"
    systemctl_log = tmp_path / "systemctl.log"
    _write_executable(
        fake_systemctl,
        """#!/bin/sh
printf '%s\n' "$*" >> "$SYSTEMCTL_LOG"
case "${1:-}" in
  is-active) exit 0 ;;
  is-failed) exit 1 ;;
  *) exit 0 ;;
esac
""",
    )
    _write_executable(fake_journalctl, "#!/bin/sh\nexit 0\n")

    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "\n".join(
            [
                "TELEGRAM_BOT_TOKEN=123456:test-token",
                "DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/test",
                "REDIS_URL=redis://127.0.0.1:6379/0",
                f"HEARTBEAT_FILE={tmp_path / 'heartbeat'}",
                "RAG_ENABLED=false",
                "",
            ]
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "APP_NAME": "release-test",
            "APP_USER": "test-user",
            "APP_GROUP": "test-group",
            "APP_ROOT": str(tmp_path / "app"),
            "RELEASES_DIR": str(tmp_path / "app" / "releases"),
            "CURRENT_LINK": str(tmp_path / "app" / "current"),
            "PREVIOUS_LINK": str(tmp_path / "app" / "previous"),
            "STATE_ROOT": str(tmp_path / "state"),
            "CACHE_ROOT": str(tmp_path / "cache"),
            "LOG_ROOT": str(tmp_path / "log"),
            "BACKUP_ROOT": str(tmp_path / "backups"),
            "ENV_FILE": str(env_file),
            "SYSTEMD_UNIT_DIR": str(tmp_path / "systemd"),
            "SYSTEMCTL_BIN": str(fake_systemctl),
            "JOURNALCTL_BIN": str(fake_journalctl),
            "SYSTEMCTL_LOG": str(systemctl_log),
            "HEALTHCHECK_ATTEMPTS": "1",
            "HEALTHCHECK_INTERVAL_SECONDS": "0",
        }
    )
    return env


def test_failed_activation_restores_previous_release_and_its_units(tmp_path: Path) -> None:
    old_release = _release(tmp_path, "old-release", "OLD-UNIT")
    new_release = _release(tmp_path, "new-release", "NEW-UNIT")
    env = _base_env(tmp_path)
    current_link = Path(env["CURRENT_LINK"])
    current_link.parent.mkdir(parents=True)
    current_link.symlink_to(new_release)

    command = f"""
set -Eeuo pipefail
source {PROJECT_ROOT / 'scripts' / 'common.sh'}
render_systemd_units_from_release {new_release}
restore_release_after_failed_activation {new_release} {old_release}
"""
    subprocess.run(["bash", "-c", command], env=env, check=True, text=True)

    assert current_link.resolve() == old_release.resolve()
    rendered = Path(env["SYSTEMD_UNIT_DIR"]) / "crop-forecast-bot.service"
    content = rendered.read_text(encoding="utf-8")
    assert "OLD-UNIT test-user" in content
    assert f"HOME={tmp_path / 'state'}" in content
    assert "@STATE_ROOT@" not in content
    systemctl_log = Path(env["SYSTEMCTL_LOG"]).read_text(encoding="utf-8")
    assert systemctl_log.count("daemon-reload") == 2
    assert "restart crop-forecast-bot.service" in systemctl_log
    assert "is-active --quiet crop-forecast-bot.service" in systemctl_log


def test_failed_initial_activation_removes_current_link_and_stops_service(
    tmp_path: Path,
) -> None:
    failed_release = _release(tmp_path, "failed-release", "FAILED-UNIT")
    env = _base_env(tmp_path)
    current_link = Path(env["CURRENT_LINK"])
    current_link.parent.mkdir(parents=True)
    current_link.symlink_to(failed_release)

    command = f"""
set -Eeuo pipefail
source {PROJECT_ROOT / 'scripts' / 'common.sh'}
if restore_release_after_failed_activation {failed_release} ''; then
  exit 99
fi
"""
    subprocess.run(["bash", "-c", command], env=env, check=True, text=True)

    assert not current_link.exists()
    systemctl_log = Path(env["SYSTEMCTL_LOG"]).read_text(encoding="utf-8")
    assert "stop crop-forecast-bot.service" in systemctl_log


def test_deploy_and_update_render_units_from_the_built_release() -> None:
    deploy = (PROJECT_ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    update = (PROJECT_ROOT / "scripts" / "update.sh").read_text(encoding="utf-8")
    rollback = (PROJECT_ROOT / "scripts" / "rollback.sh").read_text(encoding="utf-8")

    deploy_preflight = deploy.index('preflight_release "${NEW_RELEASE}"')
    deploy_render = deploy.index('render_systemd_units_from_release "${NEW_RELEASE}"')
    deploy_activate = deploy.index('activate_release "${NEW_RELEASE}"')
    assert deploy_preflight < deploy_render < deploy_activate
    assert '"${SOURCE_ROOT}/deploy/systemd/' not in deploy

    assert 'render_systemd_units_from_release "${NEW_RELEASE}"' in update
    assert 'restore_release_after_failed_activation "${NEW_RELEASE}" "${old_release}"' in update
    assert 'render_systemd_units_from_release "${target_release}"' in rollback
    assert (
        'restore_release_after_failed_activation "${target_release}" '
        '"${current_release}"'
    ) in rollback


def test_systemd_service_uses_rendered_runtime_paths() -> None:
    service = (
        PROJECT_ROOT / "deploy" / "systemd" / "crop-forecast-bot.service"
    ).read_text(encoding="utf-8")

    assert "Environment=HOME=@STATE_ROOT@" in service
    assert "Environment=XDG_CACHE_HOME=@CACHE_ROOT@" in service
    assert "ReadWritePaths=@STATE_ROOT@ @CACHE_ROOT@ @LOG_ROOT@" in service
