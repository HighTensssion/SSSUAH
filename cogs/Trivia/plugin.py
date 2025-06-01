from __future__ import annotations

from logging import log
import discord
from discord.ext import commands
from discord import app_commands
import json
import random
from core import Bot, TriviaSessionModel, TriviaStatsModel, ObjektModel
from .. import Plugin

TRIVIA_BASE_COMO = 100
TRIVIA_STREAK_BONUS = 50
TRIVIA_MAX_COMO = 10000
TRIVIA_MAX_RARITY = 5
TRIVIA_STREAKS_PER_RARITY = 5

class TriviaView(discord.ui.View):
    def __init__(self, question, correct_index, session_id, user_id, plugin):
        super().__init__(timeout=15)
        self.correct_index = correct_index
        self.session_id = session_id
        self.user_id = user_id
        self.plugin = plugin
        # for i, choice in enumerate(question["choices"]):
        #     self.add_item(discord.ui.Button(label=choice, style=discord.ButtonStyle.blurple, custom_id=str(i)))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id
    
    async def on_timeout(self):
        session = await TriviaSessionModel.get_or_none(id=self.session_id)
        if session and session.is_active:
            session.is_active = False
            await session.save()

    @discord.ui.button(label="A", style=discord.ButtonStyle.blurple, row=0)
    async def answer_button_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, 0)

    @discord.ui.button(label="B", style=discord.ButtonStyle.blurple, row=0)
    async def answer_button_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, 1)
    
    @discord.ui.button(label="C", style=discord.ButtonStyle.blurple, row=0)
    async def answer_button_c(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, 2)

    @discord.ui.button(label="D", style=discord.ButtonStyle.blurple, row=0)
    async def answer_button_d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, 3)

    async def _handle(self, interaction: discord.Interaction, index: int):
        await self.plugin.handle_trivia_answer(interaction, self.session_id, index)

class TriviaPlugin(Plugin):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        with open("data/tripleS_trivia.json", "r", encoding="utf-8") as f:
            self.questions = json.load(f)

    @app_commands.command(name="trivia", description="Answer a trivia question for a como and objekt reward!")
    @app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id,))
    async def trivia_command(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        session = await TriviaSessionModel.filter(user_id=user_id, is_active=True).first()
        if session:
            await interaction.response.send_message("You already have an active trivia question!", ephemeral=True)
            return
        
        question_index = random.randint(0, len(self.questions) - 1)
        question = self.questions[question_index]
        correct_index = question["answer"]

        session = await TriviaSessionModel.create(
            user_id=user_id,
            channel_id=interaction.channel.id,
            question_index=question_index,
            is_active=True
        )

        embed = discord.Embed(
            title="Trivia.SSS",
            description=question["question"],
            color=0x0fc
        )

        labels = ["A", "B", "C", "D"]
        choices = question["choices"]
        for i in range(0, len(choices), 2):
            line = ""
            for j in range(2):
                idx = i + j
                if idx < len(choices):
                    line += f"**{labels[idx]}:** {choices[idx]}\n"
            embed.add_field(name="\u200b", value=line, inline=True)
        
        view = TriviaView(question, correct_index, session.id, user_id, self)
        await interaction.response.send_message(embed=embed, view=view)
    
    async def handle_trivia_answer(self, interaction, session_id, selected_index):
        session = await TriviaSessionModel.get_or_none(id=session_id)
        if not session or not session.is_active:
            await interaction.response.send_message("This trivia session is no longer active.", ephemeral=True)
            return
        
        question = self.questions[session.question_index]
        correct_index = question["answer"]
        user_id = session.user_id

        session.is_active = False
        await session.save()

        stats, _ = await TriviaStatsModel.get_or_create(user_id=user_id)
        stats.total += 1
        economy_cog = self.bot.get_cog("EconomyPlugin")
        if economy_cog:
            if selected_index == correct_index:
                stats.correct += 1
                stats.streak = (stats.streak or 0) + 1

                como_reward = min(TRIVIA_BASE_COMO + (stats.streak - 1) * TRIVIA_STREAK_BONUS, TRIVIA_MAX_COMO)
                await economy_cog.update_user_balance(user_id, como_reward)
                

                if stats.streak % 50 == 0:
                    objekt_rarity = TRIVIA_MAX_RARITY + 1
                else:
                    objekt_rarity = min(stats.streak // TRIVIA_STREAKS_PER_RARITY, TRIVIA_MAX_RARITY)

                objekts = await ObjektModel.filter(rarity=objekt_rarity).all()
                if objekts:
                    objekt = random.choice(objekts)
                    await economy_cog.add_objekt_to_user(user_id, objekt)
                    count = await economy_cog.get_objekt_count(user_id, objekt)
                    objekt_msg = f"\n🎁 You also received a random rarity {objekt_rarity} objekt: **[{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}]({objekt.image_url})**!"

                    color = int(objekt.background_color.replace("#", ""), 16) if getattr(objekt, "background_color", None) else 0x0f0
                    embed = discord.Embed(
                        title="✅ Correct!",
                        description=(
                            f"Congrats {interaction.user.name}, {question['choices'][correct_index]} is correct! You earned **{como_reward:,}**! (Streak: {stats.streak})\n"
                            f"{objekt_msg}"
                        ),
                        color=color
                    )
                    if objekt.image_url:
                        embed.set_image(url=objekt.image_url)
                    embed.set_footer(text=f"You now have {count} copies of this objekt!")
                else:
                    objekt_msg = "\nNo objekt reward available at the moment."
                    embed = discord.Embed(
                        title="✅ Correct!",
                        description=(
                            f"Congrats {interaction.user.name}, {question['choices'][correct_index]} is correct! You earned **{como_reward:,}**! (Streak: {stats.streak})\n"
                            f"{objekt_msg}"
                        ),
                        color=0x0f0
                    )
                await interaction.response.send_message(embed=embed)
            else:
                stats.streak = 0
                await interaction.response.send_message(f"❌ Sorry, {interaction.user.name} Incorrect! Better luck next time!")
        else:
            await interaction.response.send_message("Economy system is not available.", ephemeral=True)
            return

        await stats.save()
    
    @trivia_command.error
    async def trivia_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            remaining = int(error.retry_after)
            minutes, seconds = divmod(remaining, 60)
            time_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
            await interaction.response.send_message(f"Trivia is on cooldown! Try again in **{time_str}**.", ephemeral=True)
        else:
            raise error



async def setup(bot: Bot): 
    await bot.add_cog(TriviaPlugin(bot))