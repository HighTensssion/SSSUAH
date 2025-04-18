from __future__ import annotations

from typing import Optional

import discord
from .. import Plugin
from core import Bot, Embed, AfkModel
from discord import Interaction, app_commands

class Utility(Plugin):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @Plugin.listener('on_message')
    async def on_afk(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        
        afk = await AfkModel.get_or_none(id=message.author.id, guild_id=message.guild.id)
        if afk:
            await message.reply(
                f"Welcome back {afk.mention}! You were afk for {afk.formatted_since}"
            )
            return await afk.delete()
        
        for user in message.mentions:
            afk = await AfkModel.get_or_none(id=user.id, guild_id=message.guild.id)
            if afk:
                await message.reply(f"{afk.mention} has been afk since {afk.formatted_since} for: {afk.reason} ")

    @app_commands.command(name='ping', description="Shows the bot's latency.")
    async def ping_command(self, interaction: Interaction):
        embed = Embed(description=f"My ping is {round(self.bot.latency*1000)}ms")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="afk", description="Set your status as AFK."
    )
    async def set_afk(self, interaction: Interaction, reason: Optional[str]):
        reason = reason or "I'm AFK!"
        record = await AfkModel.get_or_none(pk=interaction.user.id)
        if not record:
            await AfkModel.create(id=interaction.user.id, guild_id=interaction.guild_id, reason=reason)
            return await self.bot.success(
                f"Your afk has been set to {reason}",
                interaction
            )
        
        await self.bot.error(
            f"You are already afk.",
            interaction
        )

async def setup(bot: Bot) -> None:
    await bot.add_cog(Utility(bot))