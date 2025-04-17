from __future__ import annotations

from typing import Optional
from discord.ext import commands
from logging import getLogger; log = getLogger("Bot")
import discord

__all__ = (
    "Bot",
)


class Bot(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            chunk_guild_at_startup=False
        )

    async def on_ready(self) -> None:
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")

    async def success(self, content: str, interaction: discord.Interaction, ephemeral: Optional[bool]):
        """This function will send a success message."""
        pass

    async def error(self, content: str, interaction: discord.Interaction, ephemeral: Optional[bool]):
        """This function will send a success message."""
        pass