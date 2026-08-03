from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
    MenuButtonCommands,
)

logger = logging.getLogger(__name__)

# One source of truth for runtime registration, diagnostics and BotFather docs.
BOT_COMMAND_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("start", "Открыть главное меню"),
    ("crops", "Культуры активного поля"),
    ("report", "Агроотчёт выбранной культуры"),
    ("risks", "Проверить погодные условия"),
    ("pests", "Наблюдение за вредителями"),
    ("soil", "Температура почвы 0–7 см"),
    ("markers", "ОЯ и погодные маркеры вредителей"),
    ("history", "Показать историю предупреждений"),
    ("help", "Показать справку"),
    ("cancel", "Отменить текущий ввод"),
)

# Telegram may keep separate command lists for a scope and language. A stale
# all-private or language-specific list takes precedence over the default list.
# The product UI is Russian, but the same Russian command descriptions are also
# installed for users whose Telegram client language is English.
COMMAND_LANGUAGES: tuple[str, ...] = ("", "ru", "en")


@dataclass(frozen=True, slots=True)
class CommandRegistrationSnapshot:
    scope: str
    language_code: str
    commands: tuple[tuple[str, str], ...]


def build_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command=command, description=description)
        for command, description in BOT_COMMAND_DEFINITIONS
    ]


def botfather_commands_text() -> str:
    return "\n".join(
        f"{command} - {description}"
        for command, description in BOT_COMMAND_DEFINITIONS
    )


def _registration_scopes():
    return (
        BotCommandScopeDefault(),
        BotCommandScopeAllPrivateChats(),
    )


def _scope_name(scope) -> str:
    return str(scope.type)


async def inspect_bot_commands(bot: Bot) -> tuple[CommandRegistrationSnapshot, ...]:
    snapshots: list[CommandRegistrationSnapshot] = []
    for scope in _registration_scopes():
        for language_code in COMMAND_LANGUAGES:
            commands = await bot.get_my_commands(
                scope=scope,
                language_code=language_code,
            )
            snapshots.append(
                CommandRegistrationSnapshot(
                    scope=_scope_name(scope),
                    language_code=language_code,
                    commands=tuple(
                        (command.command, command.description)
                        for command in commands
                    ),
                )
            )
    return tuple(snapshots)


async def _apply_bot_commands(bot: Bot) -> None:
    commands = build_bot_commands()
    for scope in _registration_scopes():
        for language_code in COMMAND_LANGUAGES:
            await bot.set_my_commands(
                commands=commands,
                scope=scope,
                language_code=language_code,
            )

    # A previously configured Mini App menu button can hide the command list
    # even when setMyCommands succeeded. Make the default menu button explicitly
    # open Telegram's command list.
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def verify_bot_commands(bot: Bot) -> tuple[CommandRegistrationSnapshot, ...]:
    expected = BOT_COMMAND_DEFINITIONS
    snapshots = await inspect_bot_commands(bot)
    mismatches = [snapshot for snapshot in snapshots if snapshot.commands != expected]
    if mismatches:
        details = "; ".join(
            f"scope={item.scope}, lang={item.language_code or '<default>'}, "
            f"commands={len(item.commands)}"
            for item in mismatches
        )
        raise RuntimeError(f"Telegram command verification failed: {details}")

    menu_button = await bot.get_chat_menu_button()
    if getattr(menu_button, "type", None) != "commands":
        raise RuntimeError(
            "Telegram menu button is not configured to open the command list"
        )
    return snapshots


async def configure_bot_commands(
    bot: Bot,
    *,
    attempts: int = 3,
) -> tuple[CommandRegistrationSnapshot, ...]:
    """Register and verify commands before systemd readiness is announced."""

    if attempts < 1:
        raise ValueError("Command registration attempts must be positive")

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            await _apply_bot_commands(bot)
            snapshots = await verify_bot_commands(bot)
            logger.info(
                "Telegram commands registered and verified: %s commands, "
                "%s scope/language combinations",
                len(BOT_COMMAND_DEFINITIONS),
                len(snapshots),
            )
            return snapshots
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            logger.warning(
                "Telegram command registration attempt %s/%s failed: %s",
                attempt,
                attempts,
                exc,
            )
            await asyncio.sleep(float(attempt))

    raise RuntimeError(
        "Telegram commands could not be registered and verified"
    ) from last_error
