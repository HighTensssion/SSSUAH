from __future__ import annotations

from logging import log
import discord
from discord.ext import commands
from discord import app_commands
import json
import random
from core import Bot, TriviaSessionModel, TriviaStatsModel
from .. import Plugin

class TriviaPlugin(Plugin):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        with open("data/tripleS_trivia.json", "r", encoding="utf-8") as f:
            self.questions = json.load(f)

    @app_commands.command(name="trivia", description="Answer a trivia question for a como reward!")
    async def trivia_command(self, interaction: discord.Interaction):
        pass

async def setup(bot: Bot): 
    await bot.add_cog(TriviaPlugin(bot))