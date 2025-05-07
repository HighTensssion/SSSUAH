from __future__ import annotations
import asyncio
import discord
import os
import sys

from typing import Optional, Union
from .embed import Embed
from discord.ext import commands
from logging import getLogger
from tortoise import Tortoise

ALLOWED_GUILD_ID = 1340196483479371797

log = getLogger("Bot")

__all__ = ("Bot",)

@commands.command(name="sync")
@commands.is_owner()
async def sync(ctx):
    await ctx.bot.tree.sync()
    await ctx.send("Commands synced!")

@commands.command(name="reload")
@commands.is_owner()
async def reload(ctx, extension):
    await ctx.bot.unload_extension(f'cogs.{extension}.plugin')
    await ctx.bot.load_extension(f'cogs.{extension}.plugin')
    await ctx.send(f'Reloaded {extension}.plugin')

class Bot(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            chunk_guild_at_startup=False
        )
    
    async def setup_hook(self) -> None:
        await Tortoise.init(
            db_url=f"postgres://{os.getenv("user")}:{os.getenv("password")}@{os.getenv("host")}:{os.getenv("port")}/{os.getenv("dbname")}",
            modules={
                "models": ['core.models']
            }
        )
        await Tortoise.generate_schemas(safe=True)
        for file in os.listdir('cogs'):
            if not file.startswith("_"):
                await self.load_extension(f"cogs.{file}.plugin")

        synced_commands = await self.tree.sync()
        log.info(f"Successfully synced {len(synced_commands)} commands.")

        self.add_command(sync)
        self.add_command(reload)

    async def on_ready(self) -> None:
        log.info(f"Locgged in as {self.user} (ID: {self.user.id})")
        for guild in self.guilds:
            log.info(f"{guild.name} ({guild.id})")

        for guild in self.guilds:
            if guild.id != ALLOWED_GUILD_ID:
                log.info(f"Leaving unauthorized guild: {guild.name} ({guild.id})")
                await guild.leave()
                await asyncio.sleep(1)
    
    async def on_guild_join(self, guild: discord.Guild):
        if guild.id != ALLOWED_GUILD_ID:
                log.info(f"Leaving unauthorized guild: {guild.name} ({guild.id})")
                await guild.leave()
    
    async def on_guild_available(self, guild: discord.Guild):
        if guild.id != ALLOWED_GUILD_ID:
                log.info(f"Leaving unauthorized guild: {guild.name} ({guild.id})")
                await guild.leave()

    
    async def on_connect(self) -> None:
        if '-sync' in sys.argv:
            synced_commands = await self.tree.sync()
            log.info(f"Successfully synced {len(synced_commands)} commands.")

    async def success(
            self,
            message: str,
            interaction: discord.Interaction,
            *,
            ephemeral: Optional[bool] = False,
            embed: Optional[bool] = True
    ) -> Optional[discord.WebhookMessage]:
        if embed:
            if interaction.response.is_done():
                return await interaction.followup.send(
                    embed=Embed(description=message, color=discord.Colour.green()),
                    ephemeral=ephemeral
                )
            return await interaction.response.send_message(
                embed=Embed(description=message, color=discord.Colour.green()),
                ephemeral=ephemeral
            )
        else:
            if interaction.response.is_done():
                return await interaction.followup.send(content=f"✔ | {message}", ephemeral=ephemeral)
            return await interaction.response.send_message(content=f"✔ | {message}", ephemeral=ephemeral)
        
    async def error(
        self,
        message: str,
        interaction: discord.Interaction,
        *,
        ephemeral: Optional[bool] = False,
        embed: Optional[bool] = True
    ) -> Optional[discord.WebhookMessage]:
        if embed:
            if interaction.response.is_done():
                return await interaction.followup.send(
                    embed=Embed(description=message, color=discord.Colour.green()),
                    ephemeral=ephemeral
                )
            return await interaction.response.send_message(
                embed=Embed(description=message, color=discord.Colour.green()),
                ephemeral=ephemeral
            )
        else:
            if interaction.response.is_done():
                return await interaction.followup.send(content=f"❌ | {message}", ephemeral=ephemeral)
            return await interaction.response.send_message(content=f"❌ | {message}", ephemeral=ephemeral)