from __future__ import annotations

import html
import logging
import re
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)

# Telegram accepts only a small HTML subset. Preserve those tags and escape all
# remaining text, including accidental comparison signs such as ``<1 mm``.
_ALLOWED_TAG_RE = re.compile(
    r"</?(?:b|strong|i|em|u|ins|s|strike|del|span|tg-spoiler|a|code|pre|"
    r"blockquote|tg-emoji)(?:\s+[^<>]*)?>",
    flags=re.IGNORECASE,
)
_ENTITY_ERROR_MARKERS = (
    "can't parse entities",
    "unsupported start tag",
    "can't find end tag",
    "unclosed start tag",
)


def sanitize_telegram_html(text: str) -> str:
    """Escape text outside Telegram-supported HTML tags.

    Existing entities are normalized through ``unescape -> escape`` so the
    function is idempotent for report text that already contains ``&lt;``.
    """

    parts: list[str] = []
    cursor = 0
    for match in _ALLOWED_TAG_RE.finditer(text):
        plain = text[cursor : match.start()]
        parts.append(html.escape(html.unescape(plain), quote=False))
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(html.escape(html.unescape(text[cursor:]), quote=False))
    return "".join(parts)


def html_to_plain_text(text: str) -> str:
    """Remove supported markup for the emergency no-parse-mode retry."""

    return html.unescape(_ALLOWED_TAG_RE.sub("", text))


def _is_entity_error(exc: TelegramBadRequest) -> bool:
    message = str(exc).casefold()
    return any(marker in message for marker in _ENTITY_ERROR_MARKERS)


async def edit_html(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Any:
    """Edit a message with sanitized HTML and retry once as plain text."""

    sanitized = sanitize_telegram_html(text)
    try:
        return await message.edit_text(
            sanitized,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except TelegramBadRequest as exc:
        if not _is_entity_error(exc):
            raise
        logger.exception("Telegram rejected sanitized HTML; retrying as plain text")
        return await message.edit_text(
            html_to_plain_text(text),
            reply_markup=reply_markup,
            parse_mode=None,
        )


async def answer_html(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Any:
    """Send a sanitized HTML reply with a plain-text recovery path."""

    sanitized = sanitize_telegram_html(text)
    try:
        return await message.answer(
            sanitized,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except TelegramBadRequest as exc:
        if not _is_entity_error(exc):
            raise
        logger.exception("Telegram rejected sanitized HTML reply; retrying as plain text")
        return await message.answer(
            html_to_plain_text(text),
            reply_markup=reply_markup,
            parse_mode=None,
        )


async def send_html(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Any:
    """Send sanitized HTML through ``Bot`` with a plain-text recovery path."""

    sanitized = sanitize_telegram_html(text)
    try:
        return await bot.send_message(
            chat_id,
            sanitized,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except TelegramBadRequest as exc:
        if not _is_entity_error(exc):
            raise
        logger.exception("Telegram rejected sanitized HTML alert; retrying as plain text")
        return await bot.send_message(
            chat_id,
            html_to_plain_text(text),
            reply_markup=reply_markup,
            parse_mode=None,
        )
