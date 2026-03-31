"""Discord adapter implementation."""

from __future__ import annotations

from typing import Any, Optional

import discord
from discord.ext import commands

from openbridge.adapters.base import BaseAdapter, UserMessage, BotResponse, MessageType
from openbridge.adapters.registry import register_adapter
import structlog

logger = structlog.get_logger()


@register_adapter("discord")
class DiscordAdapter(BaseAdapter):
    def __init__(self, config):
        super().__init__(config)
        self.bot_token = config.bot_token
        self.guild_id = config.guild_id
        self.command_prefix = config.command_prefix
        self.allowed_roles = set(config.allowed_roles or [])

        intents = discord.Intents.default()
        intents.message_content = True

        self.bot = commands.Bot(command_prefix=self.command_prefix, intents=intents)
        self._setup_handlers()

    def _setup_handlers(self):
        @self.bot.event
        async def on_ready():
            logger.info("discord_bot_ready", user=self.bot.user.name)

        @self.bot.event
        async def on_message(message):
            if message.author == self.bot.user:
                return

            if self.guild_id and str(message.guild.id) != self.guild_id:
                return

            if self.allowed_roles:
                user_roles = {str(role.id) for role in message.author.roles}
                if not user_roles.intersection(self.allowed_roles):
                    await message.reply("You don't have permission to use this bot.")
                    return

            parsed = self._parse_message({"message": message})
            if parsed and self._message_handler:
                await self._message_handler(parsed)

        @self.bot.command(name="help")
        async def help_cmd(ctx):
            help_text = """OpenBridge - Terminal Access

Type any shell command to execute it.

Special commands:
/help - Show this help
/cancel - Cancel current operation

Sessions persist between messages."""
            await ctx.send(help_text)

    async def connect(self) -> bool:
        if not self.bot_token:
            logger.error("discord_no_token")
            return False

        try:
            await self.bot.start(self.bot_token)
            self._running = True
            return True
        except Exception as e:
            logger.error("discord_connect_error", error=str(e))
            return False

    async def disconnect(self) -> None:
        if self.bot:
            await self.bot.close()
            self._running = False
            logger.info("discord_disconnected")

    async def send_message(self, user_id: str, response: BotResponse) -> bool:
        try:
            user = await self.bot.fetch_user(int(user_id))
            if user:
                content = response.content[:2000]  # Discord limit
                await user.send(content)
                return True
        except Exception as e:
            logger.error("discord_send_error", user_id=user_id, error=str(e))
        return False

    def _parse_message(self, raw_message: dict) -> Optional[UserMessage]:
        message = raw_message.get("message")
        if not message or not isinstance(message, discord.Message):
            return None

        msg_type = MessageType.COMMAND if message.content.startswith("/") else MessageType.TEXT

        return UserMessage(
            message_id=str(message.id),
            user_id=str(message.author.id),
            platform="discord",
            content=message.content,
            message_type=msg_type,
            metadata={
                "username": str(message.author),
                "guild_id": str(message.guild.id) if message.guild else None,
                "channel_id": str(message.channel.id),
            },
        )

    def get_user_info(self, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "platform": "discord"}
