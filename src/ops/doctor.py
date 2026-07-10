from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from redis.asyncio import Redis

from config.settings import get_settings
from src.database import Database


async def check_runtime() -> list[str]:
    settings = get_settings()
    errors: list[str] = []
    try:
        settings.validate()
    except RuntimeError as exc:
        errors.append(str(exc))
        return errors

    writable_paths = {
        Path("data"),
        Path("logs"),
        settings.heartbeat_file.parent,
        settings.open_meteo_cache_path.parent,
    }
    for path in writable_paths:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            errors.append(f"Path is not writable: {path}: {exc}")

    database = Database(settings.database_url)
    try:
        await database.ping()
    except Exception as exc:
        errors.append(f"Database check failed: {exc}")
    finally:
        await database.dispose()

    if settings.redis_url:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=5)
        try:
            await redis.ping()
        except Exception as exc:
            errors.append(f"Redis check failed: {exc}")
        finally:
            await redis.aclose()
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Crop Forecast Bot diagnostics")
    parser.add_argument("--runtime", action="store_true", help="check DB, Redis and writable paths")
    args = parser.parse_args()

    if not args.runtime:
        try:
            get_settings().validate()
        except RuntimeError as exc:
            print(exc)
            return 1
        print("Configuration is valid")
        return 0

    errors = asyncio.run(check_runtime())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Runtime dependencies are available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
