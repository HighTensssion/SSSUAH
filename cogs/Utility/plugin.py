from __future__ import annotations

from typing import Optional

import discord
from .. import Plugin
from datetime import datetime, timezone
from tortoise.transactions import in_transaction
from core import Bot, Embed, CooldownModel, PityModel, ObjektModel, CollectionModel
from discord import Interaction, app_commands
from discord.ext.commands import is_owner


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

            if time_remaining.total_seconds() <=0:
                embed.add_field(
                    name=cooldown.command,
                    value="Ready",
                    inline=False
                )
                continue
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
            description=f"Your current chase objekt is **{chase_objekt.member} {chase_objekt.season[0] * int(chase_objekt.season[-1])}{chase_objekt.series}**.",
            color=int(chase_objekt.background_color.replace("#", ""), 16)
        )
        embed.set_image(url=chase_objekt.image_url)

        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="give", description="(Admin Only) Give a specific objekt to a user.")
    @app_commands.describe(
        user="The user to give the objekt to.",
        season="The season of the objekt.",
        member="The member of the objekt.",
        series="The series of the objekt."
    )
    @app_commands.choices(
        season=[
            app_commands.Choice(name="atom01", value="atom01"),
            app_commands.Choice(name="binary01", value="binary01"),
            app_commands.Choice(name="cream01", value="cream01"),
            app_commands.Choice(name="divine01", value="divine01"),
            app_commands.Choice(name="ever01", value="ever01"),
            app_commands.Choice(name="atom02", value="atom02"),
            app_commands.Choice(name="customs", value="gndsg00")
        ]
    )
    @is_owner()
    async def give_command(self, interaction: discord.Interaction, user: discord.User, season: str, member: str, series: str):
        user_id = str(user.id)
        objekt_slug = f"{season}-{member}-{series}".lower()

        # Fetch the objekt
        objekt = await ObjektModel.filter(slug=objekt_slug).first()
        if not objekt:
            await interaction.response.send_message("The specified objekt does not exist!", ephemeral=True)
            return

        # Add the objekt to the user's inventory
        async with in_transaction():
            collection_entry = await CollectionModel.filter(user_id=user_id, objekt_id=objekt.id).first()
            if collection_entry:
                collection_entry.copies += 1
                await collection_entry.save()
            else:
                await CollectionModel.create(user_id=user_id, objekt_id=objekt.id, copies=1)

        # Prepare the embed
        if objekt.background_color:
            color = int(objekt.background_color.replace("#", ""), 16)
        else:
            color = 0xFF69B4

        embed = discord.Embed(
            title=f"{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}",
            description=f"[View Objekt]({objekt.image_url})",
            color=color
        )
        embed.set_image(url=objekt.image_url)

        # Send confirmation
        await interaction.response.send_message(content=f"**{interaction.user}** has given **{user.mention}** the objekt:\n", embed=embed)
    
    @app_commands.command(name="view", description="View a specific objekt.")
    @app_commands.describe(
        season="The season of the objekt.",
        member="The member of the objekt.",
        series="The series of the objekt.",
        verbose="View all info about an objekt"
    )
    @app_commands.choices(
        season=[
            app_commands.Choice(name="atom01", value="atom01"),
            app_commands.Choice(name="binary01", value="binary01"),
            app_commands.Choice(name="cream01", value="cream01"),
            app_commands.Choice(name="divine01", value="divine01"),
            app_commands.Choice(name="ever01", value="ever01"),
            app_commands.Choice(name="atom02", value="atom02"),
            app_commands.Choice(name="customs", value="gndsg00")
        ]
    )
    async def view_command(self, interaction: discord.Interaction, season: str, member: str, series: str, verbose: bool | None = False):
        objekt_slug = f"{season}-{member}-{series}".lower()

        rarity_mapping = {
            1: "Common",
            2: "Uncommon",
            3: "Rare",
            4: "Very Rare",
            5: "Super Rare",
            6: "Ultra Rare",
            7: "Uncommon"
        }

        

        # Fetch the objekt
        objekt = await ObjektModel.filter(slug=objekt_slug).first()
        if not objekt:
            await interaction.response.send_message("The specified objekt does not exist!", ephemeral=True)
            return

        # Prepare the embed
        rarity_str = rarity_mapping.get(objekt.rarity, "")
        if objekt.background_color:
            color = int(objekt.background_color.replace("#", ""), 16)
        else:
            color = 0xFF69B4
        
        if verbose:
            embed = discord.Embed(
                title=f"{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}",
                description=f"Objekt name: {objekt.objekt_name}\nMember: {objekt.member}\nSeason: {objekt.season}\nClass: {objekt.class_}\nSeries: {objekt.series}\nRarity: {rarity_str} ({objekt.rarity})\nBorder Color: {objekt.background_color}", 
                color=color
            )
        else:
            embed = discord.Embed(
                title=f"{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}",
                color=color
            )

        embed.set_image(url=objekt.image_url)

        # Send confirmation
        await interaction.response.send_message(embed=embed)

    
async def setup(bot: Bot) -> None:
    await bot.add_cog(Utility(bot))