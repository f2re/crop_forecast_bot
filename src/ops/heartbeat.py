from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path


async def run_heartbeat(path: Path, interval_seconds: int = 15) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(str(time.time()), encoding="utf-8")
        os.replace(temporary, path)
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
