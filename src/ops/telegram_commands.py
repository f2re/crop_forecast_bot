from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from aiogram import Bot

from config.settings import get_settings
from src.bot.command_registry import (
    botfather_commands_text,
    configure_bot_commands,
    inspect_bot_commands,
    verify_bot_commands,
)


async def _run(*, apply: bool, print_botfather: bool) -> int:
    if print_botfather:
        print(botfather_commands_text())
        return 0

    settings = get_settings()
    token = settings.telegram_bot_token.strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is empty")

    bot = Bot(token=token)
    try:
        identity = await bot.get_me()
        if apply:
            snapshots = await configure_bot_commands(bot)
        else:
            snapshots = await inspect_bot_commands(bot)
            await verify_bot_commands(bot)
        menu_button = await bot.get_chat_menu_button()
        print(
            json.dumps(
                {
                    "ok": True,
                    "bot_id": identity.id,
                    "username": identity.username,
                    "menu_button": getattr(menu_button, "type", None),
                    "registrations": [asdict(item) for item in snapshots],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        await bot.session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register or verify Telegram slash commands"
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--apply",
        action="store_true",
        help="write all command scopes/languages and verify the result",
    )
    action.add_argument(
        "--check",
        action="store_true",
        help="verify existing command scopes without changing them (default)",
    )
    action.add_argument(
        "--botfather",
        action="store_true",
        help="print the exact command block for BotFather /setcommands",
    )
    args = parser.parse_args()

    try:
        return asyncio.run(
            _run(
                apply=bool(args.apply),
                print_botfather=bool(args.botfather),
            )
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
