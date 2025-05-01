from __future__ import annotations

from typing import Optional

import discord
from .. import Plugin
from datetime import datetime, timezone
from core import Bot, Embed, CooldownModel, PityModel, ObjektModel
from discord import Interaction, app_commands
from discord.ext import commands


class Utility(Plugin):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @app_commands.command(name='ping', description="Shows the bot's latency.")
    async def ping_command(self, interaction: Interaction):
        embed = Embed(description=f"My ping is {round(self.bot.latency*1000)}ms")
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="cooldowns", description="Check your current cooldowns.")
    async def cooldowns_command(self, interaction: Interaction):
        user_id = str(interaction.user.id)

        # fetch cds
        cooldowns = await CooldownModel.filter(user_id=user_id).all()

        if not cooldowns:
            await interaction.response.send_message("You currently have no active cooldowns.", ephemeral=True)
            return

        embed = Embed(
            title=f"{interaction.user.name}'s Cooldowns",
            description="Here are your current cooldowns:",
            color=0x00FF00
        )
        for cooldown in cooldowns:
            time_remaining = cooldown.expires_at - datetime.now(timezone.utc)
            days, seconds = divmod(time_remaining.total_seconds(), 86400)
            hours, remainder = divmod(seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            time_remaing_str = f"{int(days)}d {int(hours)}h {int(minutes)}m" if days > 0 else f"{int(hours)}h {int(minutes)}m"

            embed.add_field(
                name=cooldown.command,
                value=f"Time remaining: {time_remaing_str}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="chase_check", description="Check your current chase objekt.")
    async def chase_command(self, interaction: Interaction):
        user_id = str(interaction.user.id)

        # fetch chase objekt
        chase_objekt_data = await PityModel.filter(user_id=user_id).first()

        if not chase_objekt_data:
            await interaction.response.send_message ("You currently have no chase objekt set.", ephemeral=True)
            return
        
        chase_objekt = await ObjektModel.filter(slug=chase_objekt_data.chase_objekt_slug).first()

        embed = Embed(
            title=f"{interaction.user.name}'s Chase Objekt",
            description=f"Your current chase objekt is **{chase_objekt.member} {chase_objekt.season[0]}{chase_objekt.series}**.",
            color=int(chase_objekt.background_color.replace("#", ""), 16)
        )
        embed.set_image(url=chase_objekt.image_url)

        await interaction.response.send_message(embed=embed)

    
async def setup(bot: Bot) -> None:
    await bot.add_cog(Utility(bot))