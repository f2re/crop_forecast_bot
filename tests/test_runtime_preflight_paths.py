from pathlib import Path

from src.ops.doctor import _probe_writable_directory

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_writable_probe_does_not_reuse_stale_legacy_file(tmp_path: Path) -> None:
    path = tmp_path / "runtime"
    path.mkdir()
    stale_probe = path / ".write-test"
    stale_probe.write_text("created by an older root preflight", encoding="utf-8")
    stale_probe.chmod(0)

    _probe_writable_directory(path)

    assert stale_probe.exists()
    assert list(path.glob(".write-test-*")) == []


def test_deploy_and_update_repair_paths_after_release_seed_copy() -> None:
    for relative_path in ("scripts/deploy.sh", "scripts/update.sh"):
        script = _read(relative_path)
        create_release = script.rfind('create_release "${BRANCH}"')
        repair_paths = script.rfind("\nrepair_preflight_paths\n")
        build_release = script.rfind('build_release "${NEW_RELEASE}"')

        assert create_release < repair_paths < build_release, relative_path
        assert '"${STATE_ROOT}/data"' in script
        assert '"${STATE_ROOT}/data/literature"' in script
        assert '"${heartbeat_dir}"' in script
        assert 'run_as_app /usr/bin/test -w "${path}"' in script


def test_native_preflight_limits_runtime_paths_to_managed_roots() -> None:
    deploy = _read("scripts/deploy.sh")
    update = _read("scripts/update.sh")

    for script in (deploy, update):
        assert "HEARTBEAT_FILE must be inside /run/crop-forecast-bot" in script
        assert "OPEN_METEO_CACHE_PATH must be inside" in script
