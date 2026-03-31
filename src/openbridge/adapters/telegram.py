"""Telegram adapter implementation."""

from __future__ import annotations

from typing import Any, Optional

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

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
            self.application.add_handler(CommandHandler("app", self._cmd_app))
            self.application.add_handler(CommandHandler("close", self._cmd_close))
            self.application.add_handler(CommandHandler("cancel", self._cmd_cancel))
            self.application.add_handler(CommandHandler("status", self._cmd_status))
            self.application.add_handler(CommandHandler("resize", self._cmd_resize))
            # OpenCode-specific commands
            self.application.add_handler(CommandHandler("new", self._cmd_opencode_new))
            self.application.add_handler(CommandHandler("sessions", self._cmd_opencode_sessions))
            self.application.add_handler(CommandHandler("models", self._cmd_opencode_models))
            self.application.add_handler(CommandHandler("agent", self._cmd_opencode_agent))
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text)
            )
            # Add callback query handler for inline keyboards
            self.application.add_handler(CallbackQueryHandler(self._handle_callback_query))

            # Set up command menu
            await self._setup_commands()

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

    async def _setup_commands(self) -> None:
        """Set up the command menu in Telegram."""
        commands = [
            BotCommand("start", "Start the bot and show welcome message"),
            BotCommand("help", "Show help and available commands"),
            BotCommand("app", "Show app menu or switch apps"),
            BotCommand("close", "Exit current app and return to terminal"),
            BotCommand("cancel", "Cancel current operation (Ctrl+C)"),
            BotCommand("status", "Check bot and session status"),
            BotCommand("resize", "Resize terminal (usage: /resize rows cols)"),
            BotCommand("new", "Create new OpenCode session"),
            BotCommand("sessions", "List all OpenCode sessions"),
            BotCommand("models", "Show available AI models"),
            BotCommand("agent", "Show available agents"),
        ]
        await self.application.bot.set_my_commands(commands)

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
/app - Show app menu or switch apps
/close - Exit current app and return to terminal
/cancel - Cancel current operation
/resize <rows> <cols> - Resize terminal
/status - Check session status

Tips:
- Commands are executed in real shell sessions
- Sessions persist between messages
- Use Ctrl+C equivalent with /cancel
- Use /app to switch between Terminal and OpenCode"""

        await update.message.reply_text(help_text)

    async def _cmd_app(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /app command - pass to router."""
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        message = UserMessage(
            message_id=str(update.message.message_id),
            user_id=str(user.id),
            platform="telegram",
            content=update.message.text,
            message_type=MessageType.COMMAND,
            metadata={
                "chat_id": update.message.chat_id,
                "username": user.username,
                "first_name": user.first_name,
            },
        )

        if self._message_handler:
            await self._message_handler(message)

    async def _cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /close command - pass to router."""
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        message = UserMessage(
            message_id=str(update.message.message_id),
            user_id=str(user.id),
            platform="telegram",
            content="/close",
            message_type=MessageType.COMMAND,
            metadata={
                "chat_id": update.message.chat_id,
                "username": user.username,
                "first_name": user.first_name,
            },
        )

        if self._message_handler:
            await self._message_handler(message)

    async def _cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cancel command - sends Ctrl+C to terminal."""
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        # Send Ctrl+C signal through the message handler
        message = UserMessage(
            message_id=str(update.message.message_id),
            user_id=str(user.id),
            platform="telegram",
            content="/cancel",
            message_type=MessageType.COMMAND,
            metadata={
                "chat_id": update.message.chat_id,
                "username": user.username,
                "first_name": user.first_name,
            },
        )

        if self._message_handler:
            await self._message_handler(message)
            await update.message.reply_text("Sent Ctrl+C to terminal")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        status_text = """OpenBridge Status

Bot: Online ✅
Platform: Telegram
User: {}

Send any command to execute it in your terminal.""".format(user.first_name)

        await update.message.reply_text(status_text)

    async def _cmd_resize(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /resize command."""
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        # Parse arguments
        args = update.message.text.split()
        if len(args) == 3:
            try:
                rows = int(args[1])
                cols = int(args[2])

                # Send resize command through the message handler
                message = UserMessage(
                    message_id=str(update.message.message_id),
                    user_id=str(user.id),
                    platform="telegram",
                    content=f"/resize {rows} {cols}",
                    message_type=MessageType.COMMAND,
                    metadata={
                        "chat_id": update.message.chat_id,
                        "username": user.username,
                        "first_name": user.first_name,
                    },
                )

                if self._message_handler:
                    await self._message_handler(message)
                    await update.message.reply_text(f"Terminal resized to {rows}x{cols}")
            except ValueError:
                await update.message.reply_text(
                    "Usage: /resize <rows> <cols>\nExample: /resize 24 80"
                )
        else:
            await update.message.reply_text("Usage: /resize <rows> <cols>\nExample: /resize 24 80")

    async def _cmd_opencode_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /new command - Create new OpenCode session."""
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        message = UserMessage(
            message_id=str(update.message.message_id),
            user_id=str(user.id),
            platform="telegram",
            content="/new",
            message_type=MessageType.COMMAND,
            metadata={
                "chat_id": update.message.chat_id,
                "username": user.username,
                "first_name": user.first_name,
            },
        )

        if self._message_handler:
            await self._message_handler(message)

    async def _cmd_opencode_sessions(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /sessions command - Show inline keyboard with sessions."""
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        # Fetch sessions from OpenBridge API (we'll need to get them from the app)
        # For now, show a message explaining how to use it
        keyboard = [
            [InlineKeyboardButton("🆕 Create New Session", callback_data="session:new")],
            [InlineKeyboardButton("📋 List All Sessions", callback_data="session:list")],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📁 Session Manager\n\nChoose an action:", reply_markup=reply_markup
        )

        # Also send the command to router for actual processing
        message = UserMessage(
            message_id=str(update.message.message_id),
            user_id=str(user.id),
            platform="telegram",
            content="/sessions",
            message_type=MessageType.COMMAND,
            metadata={
                "chat_id": update.message.chat_id,
                "username": user.username,
                "first_name": user.first_name,
            },
        )

        if self._message_handler:
            await self._message_handler(message)

    async def _cmd_opencode_models(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /models command - Show inline keyboard with models."""
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        # Show inline keyboard with popular models
        # We'll fetch real models from the API when the user taps
        keyboard = [
            [
                InlineKeyboardButton(
                    "🤖 Kimi K2.5 (Default)", callback_data="model:opencode-go:kimi-k2.5"
                )
            ],
            [
                InlineKeyboardButton(
                    "🧠 Gemini 2.5 Pro", callback_data="model:google:gemini-2.5-pro"
                )
            ],
            [InlineKeyboardButton("🎯 GPT-4o", callback_data="model:openai:gpt-4o")],
            [
                InlineKeyboardButton(
                    "🔮 Claude 4 Sonnet", callback_data="model:anthropic:claude-4-sonnet"
                )
            ],
            [InlineKeyboardButton("📋 Show All Models", callback_data="model:list")],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🤖 Select a Model\n\nTap a model to switch:", reply_markup=reply_markup
        )

    async def _cmd_opencode_agent(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /agent command - List available agents."""
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        message = UserMessage(
            message_id=str(update.message.message_id),
            user_id=str(user.id),
            platform="telegram",
            content="/agent",
            message_type=MessageType.COMMAND,
            metadata={
                "chat_id": update.message.chat_id,
                "username": user.username,
                "first_name": user.first_name,
            },
        )

        if self._message_handler:
            await self._message_handler(message)

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        if self.allowed_users and user.id not in self.allowed_users:
            await update.message.reply_text("You are not authorized.")
            return

        message = self._parse_message({"update": update})
        if message and self._message_handler:
            await self._message_handler(message)

    async def _handle_callback_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle inline keyboard button callbacks."""
        query = update.callback_query
        await query.answer()  # Acknowledge the callback

        callback_data = query.data
        user = query.from_user

        if self.allowed_users and user.id not in self.allowed_users:
            await query.edit_message_text("You are not authorized.")
            return

        # Parse callback data
        if callback_data.startswith("model:"):
            parts = callback_data.split(":")
            if len(parts) >= 2:
                action = parts[1]
                if action == "list":
                    # Send /models command to get full list
                    message = UserMessage(
                        message_id=str(query.message.message_id),
                        user_id=str(user.id),
                        platform="telegram",
                        content="/models",
                        message_type=MessageType.COMMAND,
                        metadata={
                            "chat_id": query.message.chat_id,
                            "username": user.username,
                            "first_name": user.first_name,
                        },
                    )
                    if self._message_handler:
                        await self._message_handler(message)
                        await query.edit_message_text("📋 Loading models list...")
                else:
                    # Switch to specific model
                    provider_id = parts[1]
                    model_id = parts[2] if len(parts) > 2 else "default"

                    # Create message with model switch command
                    message = UserMessage(
                        message_id=str(query.message.message_id),
                        user_id=str(user.id),
                        platform="telegram",
                        content=f"/model {provider_id}:{model_id}",
                        message_type=MessageType.COMMAND,
                        metadata={
                            "chat_id": query.message.chat_id,
                            "username": user.username,
                            "first_name": user.first_name,
                            "model_provider": provider_id,
                            "model_id": model_id,
                        },
                    )
                    if self._message_handler:
                        await self._message_handler(message)
                        await query.edit_message_text(f"🤖 Switched to {model_id}")

        elif callback_data.startswith("session:"):
            parts = callback_data.split(":")
            if len(parts) >= 2:
                action = parts[1]
                if action == "new":
                    # Create new session
                    message = UserMessage(
                        message_id=str(query.message.message_id),
                        user_id=str(user.id),
                        platform="telegram",
                        content="/new",
                        message_type=MessageType.COMMAND,
                        metadata={
                            "chat_id": query.message.chat_id,
                            "username": user.username,
                            "first_name": user.first_name,
                        },
                    )
                    if self._message_handler:
                        await self._message_handler(message)
                        await query.edit_message_text("🆕 Creating new session...")
                elif action == "list":
                    # List all sessions
                    message = UserMessage(
                        message_id=str(query.message.message_id),
                        user_id=str(user.id),
                        platform="telegram",
                        content="/sessions",
                        message_type=MessageType.COMMAND,
                        metadata={
                            "chat_id": query.message.chat_id,
                            "username": user.username,
                            "first_name": user.first_name,
                        },
                    )
                    if self._message_handler:
                        await self._message_handler(message)
                        await query.edit_message_text("📁 Loading sessions...")
                elif action == "switch" and len(parts) > 2:
                    # Switch to specific session
                    session_id = parts[2]
                    message = UserMessage(
                        message_id=str(query.message.message_id),
                        user_id=str(user.id),
                        platform="telegram",
                        content=f"/session {session_id}",
                        message_type=MessageType.COMMAND,
                        metadata={
                            "chat_id": query.message.chat_id,
                            "username": user.username,
                            "first_name": user.first_name,
                            "target_session_id": session_id,
                        },
                    )
                    if self._message_handler:
                        await self._message_handler(message)
                        await query.edit_message_text(f"🔄 Switching to session...")

    def get_user_info(self, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "platform": "telegram"}
