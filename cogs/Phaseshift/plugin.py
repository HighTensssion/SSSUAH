from __future__ import annotations

from logging import log
import os
import asyncio
import discord
import random
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import requests
from core import Bot, EconomyModel, ObjektModel, CollectionModel, CooldownModel, ShopModel, PityModel
from core.constants import SEASON_CHOICES, BANNER_CHOICES, RARITY_COMO_REWARDS, RARITY_STR_MAPPING, RARITY_TIERS, SHOP_BUY_VALUES, SORT_CHOICES, CLASS_CHOICES, RARITY_CHOICES
from tortoise.exceptions import DoesNotExist
from tortoise.transactions import in_transaction
from tortoise.expressions import Q
from tortoise.functions import Max
from datetime import datetime, timedelta, tzinfo, timezone, time
import aiohttp
from .. import Plugin
from discord import app_commands
from discord.ext import tasks
from discord.ui import View, Button



class PhaseshiftPlugin(Plugin):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ps_playlist", description="The Phase Shift playlist.")
    async def ps_playlist_command(self, interaction: discord.Interaction):
        await interaction.response.send_message("[PS!PLAYLIST](https://open.spotify.com/playlist/2mW2Cp2weczPQ5XBpB2cmE?si=4df6faeabcb84a5d)")

    @app_commands.command(name="phase_shift", description="A link to Phase Shift.")
    async def phase_shift_command(self, interaction: discord.Interaction):
        await  interaction.response.send_message("[Phase Shift AU](https://archiveofourown.org/works/65293858/chapters/167983609)")

    @app_commands.command(name="pairings_table", description="The tripleS pairings table.")
    async def pairings_table_command(self, interaction: discord.Interaction):
        await interaction.response.send_message("[tripleS Pairings](https://astralthegate.carrd.co/#pairings)")

    @app_commands.command(name="astral", description="A link to astral.")
    async def astral_command(self, interaction: discord.Interaction):
        await interaction.response.send_message("[A2tr4l](https://astralthegate.carrd.co)")

async def setup(bot: Bot): 
    await bot.add_cog(PhaseshiftPlugin(bot))