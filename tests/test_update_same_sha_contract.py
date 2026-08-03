from pathlib import Path


def test_same_sha_update_verifies_running_release_before_exit() -> None:
    script = Path("scripts/update.sh").read_text(encoding="utf-8")

    assert "service_process_release" in script
    assert 'readlink -f "/proc/${pid}/cwd"' in script
    assert "restart_current_release" in script
    assert '"${running_release}" != "${old_release}"' in script
    assert "heartbeat_is_fresh" in script


def test_same_sha_can_be_forced_through_full_redeployment() -> None:
    script = Path("scripts/update.sh").read_text(encoding="utf-8")

    assert "FORCE_REDEPLOY" in script
    assert 'is_true_value "${FORCE_REDEPLOY:-false}"' in script
    assert "Forcing a full redeployment" in script
