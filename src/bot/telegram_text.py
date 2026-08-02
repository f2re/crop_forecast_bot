from __future__ import annotations

import html
import logging
import re
from typing import Any

from aiogram import Bot
from aiogram.client.default import Default
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


def _uses_default_or_explicit_html(method: Any) -> bool:
    parse_mode = getattr(method, "parse_mode", None)
    return parse_mode == ParseMode.HTML or isinstance(parse_mode, Default)


def _prepare_method_text(method: Any, *, plain: bool = False) -> Any:
    """Copy an aiogram method with safe text/caption without mutating caller state."""

    updates: dict[str, Any] = {}
    for field_name in ("text", "caption"):
        value = getattr(method, field_name, None)
        if isinstance(value, str):
            updates[field_name] = (
                html_to_plain_text(value) if plain else sanitize_telegram_html(value)
            )
    if plain:
        updates["parse_mode"] = None
        if hasattr(method, "entities"):
            updates["entities"] = None
        if hasattr(method, "caption_entities"):
            updates["caption_entities"] = None
    if not updates:
        return method
    return method.model_copy(update=updates)


class SafeHtmlBot(Bot):
    """Bot that prevents one malformed report line from breaking Telegram UX.

    The application uses HTML as its default parse mode. Every text/caption is
    sanitized immediately before the API request. If Telegram still rejects
    entities, the same request is retried once as plain text. This also protects
    background scheduler messages that are not sent through handler helpers.
    """

    async def __call__(self, method: Any, request_timeout: int | None = None) -> Any:
        prepared = method
        if _uses_default_or_explicit_html(method):
            prepared = _prepare_method_text(method)
        try:
            return await super().__call__(prepared, request_timeout=request_timeout)
        except TelegramBadRequest as exc:
            if not _is_entity_error(exc):
                raise
            logger.warning(
                "Telegram rejected message entities; retrying once as plain text",
                exc_info=True,
            )
            return await super().__call__(
                _prepare_method_text(method, plain=True),
                request_timeout=request_timeout,
            )


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
        logger.warning("Telegram rejected sanitized HTML; retrying as plain text")
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
        logger.warning("Telegram rejected sanitized HTML reply; retrying as plain text")
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
        logger.warning("Telegram rejected sanitized HTML alert; retrying as plain text")
        return await bot.send_message(
            chat_id,
            html_to_plain_text(text),
            reply_markup=reply_markup,
            parse_mode=None,
        )
