import time
from pathlib import Path

from src.ops.heartbeat import check_heartbeat


def test_recent_heartbeat_is_healthy(tmp_path: Path) -> None:
    heartbeat = tmp_path / "heartbeat"
    heartbeat.write_text(str(time.time()), encoding="utf-8")
    assert check_heartbeat(heartbeat, max_age_seconds=10)


def test_missing_or_stale_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert not check_heartbeat(missing, max_age_seconds=10)

    stale = tmp_path / "stale"
    stale.write_text(str(time.time() - 100), encoding="utf-8")
    assert not check_heartbeat(stale, max_age_seconds=10)
