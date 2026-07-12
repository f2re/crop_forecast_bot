from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Chat, Message, Update, User


class RecordingSession(BaseSession):
    """In-memory Telegram API session for Dispatcher scenario tests."""

    def __init__(self, *, fail_edit_message: bool = False) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self._next_message_id = 10_000
        self._fail_edit_message = fail_edit_message

    @property
    def texts(self) -> list[str]:
        return [
            method.text
            for method in self.calls
            if isinstance(method, (SendMessage, EditMessageText))
        ]

    async def close(self) -> None:
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65_536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        if False:  # pragma: no cover - required async-generator shape
            yield b""

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        self.calls.append(method)
        if isinstance(method, EditMessageText) and self._fail_edit_message:
            self._fail_edit_message = False
            raise TelegramBadRequest(
                method=method,
                message="Bad Request: message to edit not found",
            )
        if isinstance(method, (SendMessage, EditMessageText)):
            self._next_message_id += 1
            chat_id = int(getattr(method, "chat_id", 0) or 1001)
            return Message.model_validate(
                {
                    "message_id": self._next_message_id,
                    "date": int(datetime.now(timezone.utc).timestamp()),
                    "chat": {"id": chat_id, "type": "private"},
                    "from": {
                        "id": bot.id,
                        "is_bot": True,
                        "first_name": "Test Bot",
                    },
                    "text": method.text,
                },
                context={"bot": bot},
            )
        if isinstance(method, AnswerCallbackQuery):
            return True
        return True


def make_bot(session: RecordingSession | None = None) -> Bot:
    return Bot("123456:TEST_TOKEN", session=session or RecordingSession())


def message_update(
    update_id: int,
    *,
    user_id: int = 1001,
    text: str,
    message_id: int | None = None,
) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=message_id or update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=user_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="Farmer"),
            text=text,
        ),
    )


def callback_update(
    update_id: int,
    *,
    data: str,
    user_id: int = 1001,
    callback_id: str | None = None,
    message_id: int = 500,
) -> Update:
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=callback_id or f"callback-{update_id}",
            from_user=User(id=user_id, is_bot=False, first_name="Farmer"),
            chat_instance=f"chat-instance-{user_id}",
            message=Message(
                message_id=message_id,
                date=datetime.now(timezone.utc),
                chat=Chat(id=user_id, type="private"),
                text="menu",
            ),
            data=data,
        ),
    )
