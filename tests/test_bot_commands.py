from __future__ import annotations

import pytest
from aiogram.types import BotCommand, MenuButtonDefault

from src.bot.command_registry import (
    BOT_COMMAND_DEFINITIONS,
    botfather_commands_text,
    configure_bot_commands,
    telegram_type_value,
    verify_bot_commands,
)


class _FakeBot:
    def __init__(self) -> None:
        self.commands: dict[tuple[str, str], list[BotCommand]] = {}
        self.menu_button = MenuButtonDefault()
        self.set_calls: list[tuple[str, str]] = []

    async def set_my_commands(self, commands, *, scope, language_code=""):
        key = (telegram_type_value(scope.type), language_code)
        self.commands[key] = [
            BotCommand(command=item.command, description=item.description)
            for item in commands
        ]
        self.set_calls.append(key)
        return True

    async def get_my_commands(self, *, scope, language_code=""):
        return self.commands.get(
            (telegram_type_value(scope.type), language_code),
            [],
        )

    async def set_chat_menu_button(self, *, menu_button, chat_id=None):
        assert chat_id is None
        self.menu_button = menu_button
        return True

    async def get_chat_menu_button(self, *, chat_id=None):
        assert chat_id is None
        return self.menu_button


@pytest.mark.asyncio
async def test_registration_covers_default_private_and_languages() -> None:
    bot = _FakeBot()

    snapshots = await configure_bot_commands(bot)  # type: ignore[arg-type]

    assert set(bot.set_calls) == {
        ("default", ""),
        ("default", "ru"),
        ("default", "en"),
        ("all_private_chats", ""),
        ("all_private_chats", "ru"),
        ("all_private_chats", "en"),
    }
    assert len(snapshots) == 6
    assert telegram_type_value(bot.menu_button.type) == "commands"
    for commands in bot.commands.values():
        assert tuple(
            (item.command, item.description) for item in commands
        ) == BOT_COMMAND_DEFINITIONS


@pytest.mark.asyncio
async def test_verification_rejects_stale_language_specific_list() -> None:
    bot = _FakeBot()
    await configure_bot_commands(bot)  # type: ignore[arg-type]
    bot.commands[("all_private_chats", "ru")] = [
        BotCommand(command="start", description="Старый список")
    ]

    with pytest.raises(RuntimeError, match="scope=all_private_chats, lang=ru"):
        await verify_bot_commands(bot)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_verification_rejects_hidden_command_menu() -> None:
    bot = _FakeBot()
    await configure_bot_commands(bot)  # type: ignore[arg-type]
    bot.menu_button = MenuButtonDefault()

    with pytest.raises(RuntimeError, match="menu button"):
        await verify_bot_commands(bot)  # type: ignore[arg-type]


def test_botfather_block_matches_runtime_registry() -> None:
    lines = botfather_commands_text().splitlines()

    assert len(lines) == len(BOT_COMMAND_DEFINITIONS)
    assert lines[0] == "start - Открыть главное меню"
    assert lines[-1] == "cancel - Отменить текущий ввод"
    assert all(not line.startswith("/") for line in lines)
    assert len({command for command, _ in BOT_COMMAND_DEFINITIONS}) == len(
        BOT_COMMAND_DEFINITIONS
    )
    assert all(1 <= len(command) <= 32 for command, _ in BOT_COMMAND_DEFINITIONS)
    assert all(1 <= len(description) <= 256 for _, description in BOT_COMMAND_DEFINITIONS)
