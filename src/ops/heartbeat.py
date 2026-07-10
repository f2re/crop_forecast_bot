from __future__ import annotations

import argparse
import asyncio
import os
import socket
import time
from pathlib import Path


def notify_systemd(message: str) -> bool:
    """Send a notification to systemd without an external dependency.

    Outside a ``Type=notify`` service ``NOTIFY_SOCKET`` is absent and this
    function is a no-op, which keeps local development and tests portable.
    """

    notify_socket = os.getenv("NOTIFY_SOCKET")
    if not notify_socket:
        return False

    address = "\0" + notify_socket[1:] if notify_socket.startswith("@") else notify_socket
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
            client.connect(address)
            client.sendall(message.encode("utf-8"))
    except OSError:
        return False
    return True


def notify_ready() -> bool:
    return notify_systemd("READY=1\nSTATUS=Polling Telegram and scheduler are active")


def notify_stopping() -> bool:
    return notify_systemd("STOPPING=1\nSTATUS=Shutting down cleanly")


async def run_heartbeat(path: Path, interval_seconds: int = 15) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(str(time.time()), encoding="utf-8")
        os.replace(temporary, path)
        notify_systemd("WATCHDOG=1")
        await asyncio.sleep(interval_seconds)


def check_heartbeat(path: Path, max_age_seconds: int = 90) -> bool:
    try:
        timestamp = float(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError):
        return False
    return time.time() - timestamp <= max_age_seconds


def main() -> int:
    parser = argparse.ArgumentParser(description="Crop Forecast Bot heartbeat check")
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-age", type=int, default=90)
    args = parser.parse_args()
    return 0 if check_heartbeat(args.path, args.max_age) else 1


if __name__ == "__main__":
    raise SystemExit(main())
