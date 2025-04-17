from __future__ import annotations

import discord
from core import Bot, EconomyModel
from tortoise.exceptions import DoesNotExist
from .. import Plugin
from discord import app_commands

class EconomyPlugin(Plugin):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    
    async def get_user_data(self, id: int) -> EconomyModel:
        try:
            return await EconomyModel.get(pk=id)
        except DoesNotExist:
            return await EconomyModel.create(id=id)
    
    @app_commands.command(
        name="balance", description="Show your balance or another user's balance."
    )
    async def balance_command(self, interaction: discord.Interaction, user: discord.User | None):
        target = user or interaction.user
        data = await self.get_user_data(id=target.id)
        prefix = f"Your ({user})" if not user else f"{user}'s"
        await self.bot.success(
            f"{prefix} total balance is: **{data.balance:.2f}**", interaction
        )

async def setup(bot: Bot):
    await bot.add_cog(EconomyPlugin(bot))