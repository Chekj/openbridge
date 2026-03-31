"""Telegram adapter implementation."""

from __future__ import annotations

from typing import Any, Optional

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from openbridge.adapters.base import BaseAdapter, UserMessage, BotResponse, MessageType
from openbridge.adapters.registry import register_adapter
import structlog

logger = structlog.get_logger()


@register_adapter("telegram")
class TelegramAdapter(BaseAdapter):
    def __init__(self, config):
        super().__init__(config)
        self.bot_token = config.bot_token
        self.allowed_users = set(config.allowed_users or [])
        self.application: Optional[Application] = None

    async def connect(self) -> bool:
        if not self.bot_token:
            logger.error("telegram_no_token")
            return False

        try:
            self.application = Application.builder().token(self.bot_token).build()

            # Add handlers
            self.application.add_handler(CommandHandler("start", self._cmd_start))
            self.application.add_handler(CommandHandler("help", self._cmd_help))
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text)
            )

            await self.application.initialize()
            await self.application.start()

            # Start polling
            await self.application.updater.start_polling()

            self._running = True
            logger.info("telegram_connected")
            return True
        except Exception as e:
            logger.error("telegram_connect_error", error=str(e))
            return False

    async def disconnect(self) -> None:
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            self._running = False
            logger.info("telegram_disconnected")

    async def send_message(self, user_id: str, response: BotResponse) -> bool:
        if not self.application:
            return False

        try:
            await self.application.bot.send_message(
                chat_id=user_id, text=response.content[:4096], parse_mode=response.parse_mode
            )
            return True
        except Exception as e:
            logger.error("telegram_send_error", user_id=user_id, error=str(e))
            return False

    def _parse_message(self, raw_message: dict) -> Optional[UserMessage]:
        update = raw_message.get("update")
        if not update or not isinstance(update, Update):
            return None

        message = update.message or update.edited_message
        if not message or not message.text:
            return None

        msg_type = MessageType.COMMAND if message.text.startswith("/") else MessageType.TEXT

        return UserMessage(
            message_id=str(message.message_id),
            user_id=str(message.from_user.id),
            platform="telegram",
            content=message.text,
            message_type=msg_type,
            metadata={
                "chat_id": message.chat_id,
                "username": message.from_user.username,
                "first_name": message.from_user.first_name,
            },
        )

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        welcome_text = f"""Welcome to OpenBridge, {user.first_name}!

You can now use your terminal from Telegram.

Commands:
/help - Show help
/status - Check connection status

Just type any command to execute it."""

        await update.message.reply_text(welcome_text)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        help_text = """OpenBridge - Terminal Access

Just type any shell command and it will be executed.

Special commands:
/help - Show this help
/cancel - Cancel current operation
/resize <rows> <cols> - Resize terminal

Tips:
- Commands are executed in real shell sessions
- Sessions persist between messages
- Use Ctrl+C equivalent with /cancel"""

        await update.message.reply_text(help_text)

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        message = self._parse_message({"update": update})
        if message and self._message_handler:
            await self._message_handler(message)

    def get_user_info(self, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "platform": "telegram"}
