from __future__ import annotations

import random
from typing import Optional

import discord
import os
from PIL import Image
import requests
import aiohttp
from io import BytesIO
from .. import Plugin
from datetime import datetime, timezone
from tortoise.transactions import in_transaction
from core import Bot, Embed, CooldownModel, PityModel, ObjektModel, CollectionModel, EconomyModel
from core.constants import SEASON_CHOICES, RARITY_MAPPING, MEMBER_PRIORITY, CLASS_CHOICES, RARITY_CHOICES, SORT_CHOICES, RARITY_COMO_REWARDS
from discord import Interaction, app_commands
from discord.ext.commands import is_owner
from discord.ui import View, Button

class Utility(Plugin):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.cache = {}
    
    async def check_admin_permissions(self, interaction: discord.Interaction) -> bool:
        if await interaction.client.is_owner(interaction.user) or interaction.user.guild_permissions.administrator:
            return True
        await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
        return False

    async def create_embed(self, title: str, description: str, color: int = 0x00FF00, fields: list[tuple[str, str]] = None) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color)
        if fields:
            for name, value in fields:
                embed.add_field(name=name, value=value, inline=False)
        return embed

    async def update_user_balance(self, user_id: int, amount: int) -> EconomyModel:
        user_data, _ = await EconomyModel.get_or_create(id=user_id)
        user_data.balance += amount
        await user_data.save()
        return user_data
    
    async def format_time_remaining(self, expires_at: datetime) -> str:
        time_remaining = expires_at - datetime.now(timezone.utc)
        total_seconds = time_remaining.total_seconds()
        if total_seconds <= 0:
            return "Ready"
        days, seconds = divmod(total_seconds, 86400)
        hours, remainder = divmod(seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{int(days)}d {int(hours)}h {int(minutes)}m" if days > 0 else f"{int(hours)}h {int(minutes)}m"

    def determine_grid_size(self, num_objekts: int) -> tuple[int, int]:
        if num_objekts == 1:
            return (1, 1)
        elif num_objekts <= 4:
            return (2, 2)
        elif num_objekts <= 8:
            return (4, 2)
        elif num_objekts <= 10:
            return (5, 2)
        elif num_objekts <= 12:
            return (4, 3)
        elif num_objekts <= 16:
            return (4, 4)
        elif num_objekts <= 20:
            return (5, 4)
        else:
            return (6, 4)

    async def generate_collage(self, season: str, series: str, page: int, page_objekts: list, grid_size: tuple[int, int]) -> tuple[str, str]:
        base_dir = "collage"
        series_dir = os.path.join(base_dir, "series")
        os.makedirs(series_dir, exist_ok=True)

        filename = os.path.join(series_dir, f"collage_{season}_{series}_page_{page}.png")
        cache_key = f"{season}_{series}_page_{page}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        thumb_size = (200, 300)
        gap = 10
        edge_padding = 20
        collage_width = (thumb_size[0] + gap) * grid_size[0] - gap + 2 * edge_padding
        collage_height = (thumb_size[1] + gap) * grid_size[1] - gap + 2 * edge_padding

        background_color = self.get_background_color(page_objekts)
        collage = Image.new('RGBA', (collage_width, collage_height), background_color)

        async with aiohttp.ClientSession() as session:
            for index, objekt in enumerate(page_objekts):
                try:
                    async with session.get(objekt.image_url, timeout=10) as response:
                        response.raise_for_status()
                        img_data = await response.read()
                        img = Image.open(BytesIO(img_data))
                        img.thumbnail(thumb_size)

                        x = edge_padding + (index % grid_size[0]) * (thumb_size[0] + gap)
                        y = edge_padding + (index // grid_size[0]) * (thumb_size[1] + gap)
                        collage.paste(img, (x, y))
                except Exception as e:
                    print(f"Error loading image from {objekt.image_url}: {e}")

        collage.save(filename, format='PNG')

        names = [f"**{objekt.member}**" for objekt in page_objekts]
        description = "\n".join(
            [", ".join(names[i:i + grid_size[0]]) for i in range(0, len(names), grid_size[0])]
        )

        self.cache[cache_key] = (filename, description)
        return filename, description

    def get_background_color(self, page_objekts: list) -> tuple[int, int, int, int]:
        """Calculate the background color based on the first objekt's color."""
        if page_objekts and page_objekts[0].background_color:
            base_color = int(page_objekts[0].background_color.replace("#", ""), 16)
            original_r = (base_color >> 16) & 0xFF
            original_g = (base_color >> 8) & 0xFF
            original_b = base_color & 0xFF

            r = int(original_r * 0.8)
            g = int(original_g * 0.8)
            b = int(original_b * 0.8)
            return (r, g, b, 255)
        return (255, 255, 255, 255)

    async def generate_leaderboard_data(self, users, total_objekts_ids, mode):
        leaderboard_data = []
        for user in users:
            user_id = str(user.id)
            discord_user = await self.bot.fetch_user(user_id)
            user_name = discord_user.name if discord_user else "Unknown User"

            collected_objekts = await CollectionModel.filter(user_id=user_id, objekt__id__in=total_objekts_ids).prefetch_related("objekt")

            if mode and mode.value == "copies":
                total_copies = sum(entry.copies for entry in collected_objekts)
                leaderboard_data.append((user_id, user_name, total_copies))
            else:
                collected_ids = {entry.objekt.id for entry in collected_objekts}
                collected_count = len(collected_ids)
                total_count = len(total_objekts_ids)
                percent_complete = (collected_count / total_count) * 100 if total_count > 0 else 0
                leaderboard_data.append((user_id, user_name, percent_complete, collected_count, total_count))

        return sorted(leaderboard_data, key=lambda x: x[2], reverse=True)

    def get_leaderboard_title(self, mode, member, season):
        embed_title = "GNDSG Slur Gacha Leaderboard"
        if mode and mode.value == "copies":
            embed_title += " by Copies"
        else:
            embed_title += " by Percent Complete"
        if member:
            embed_title += f" ({member})"
        elif season:
            embed_title += f" ({season.value})"
        return embed_title

    def add_leaderboard_fields(self, embed, leaderboard_data, mode):
        for rank, entry in enumerate(leaderboard_data[:10], start=1):
            if mode and mode.value == "copies":
                user_id, user_name, total_copies = entry
                embed.add_field(name=f"#{rank} {user_name}", value=f"**{total_copies}** copies held", inline=False)
            else:
                user_id, user_name, percent_complete, collected_count, total_count = entry
                embed.add_field(name=f"#{rank} {user_name}", value=f"**({collected_count}/{total_count})** | **{percent_complete:.2f}%** complete", inline=False)

    def select_objekts_to_give(self, unowned_objekts, all_objekts, amount):
        if len(unowned_objekts) >= amount:
            return random.sample(unowned_objekts, amount)
        else:
            selected_objekts = unowned_objekts
            remaining_amount = amount - len(unowned_objekts)
            owned_objekts_to_add = random.choices(all_objekts, k=remaining_amount)
            selected_objekts.extend(owned_objekts_to_add)
            return selected_objekts

    def calculate_como_reward(self, rarity_value, amount):
        return RARITY_COMO_REWARDS.get(rarity_value, 0) * amount

    async def perform_objekt_transaction(self, user_id, selected_objekts, total_como_reward):
        async with in_transaction():
            for objekt in selected_objekts:
                collection_entry = await CollectionModel.filter(user_id=user_id, objekt_id=objekt.id).first()
                if collection_entry:
                    collection_entry.copies += 1
                    await collection_entry.save()
                else:
                    await CollectionModel.create(user_id=user_id, objekt_id=objekt.id, copies=1)

            user_data, _ = await EconomyModel.get_or_create(id=user_id)
            user_data.balance += total_como_reward
            await user_data.save()

    async def fetch_filtered_inventory(self, user_id: str, member: str | None, season: app_commands.Choice[str] | None,
                                   rarity: app_commands.Choice[int] | None, class_: app_commands.Choice[str] | None):
        query = CollectionModel.filter(user_id=user_id).prefetch_related("objekt")
        if member:
            query = query.filter(objekt__member__iexact=member)
        if season:
            query = query.filter(objekt__season__iexact=season.value)
        if rarity:
            query = query.filter(objekt__rarity__iexact=rarity.value)
        if class_:
            query = query.filter(objekt__class___iexact=class_.value)
        return await query

    async def create_confirmation_embed(self, duplicates_to_send, recipient_name: str):
        embed = await self.create_embed(
            title=f"Confirm Sending Duplicates to {recipient_name}",
            description="The following objekts will be sent:",
            fields=[
                (f"{entry.objekt.member} {entry.objekt.season[0] * int(entry.objekt.season[-1])}{entry.objekt.series}",
                f"Rarity: {entry.objekt.rarity}, Class: {entry.objekt.class_}")
                for entry in duplicates_to_send[:8]
            ],
            color=0xFFA500
        )
        if len(duplicates_to_send) > 8:
            remaining_count = len(duplicates_to_send) - 8
            embed.add_field(name="And ...", value=f"{remaining_count} more objekts will be sent.", inline=False)
        return embed

    async def perform_duplicates_transaction(self, sender_id: str, recipient_id: str, duplicates_to_send):
        async with in_transaction():
            for entry in duplicates_to_send:
                entry.copies -= 1
                await entry.save()

                recipient_entry = await CollectionModel.filter(user_id=recipient_id, objekt_id=entry.objekt.id).first()
                if recipient_entry:
                    recipient_entry.copies += 1
                    await recipient_entry.save()
                else:
                    await CollectionModel.create(user_id=recipient_id, objekt_id=entry.objekt.id, copies=1)

    async def create_success_embed(self, sender_name: str, recipient_name: str, duplicates_to_send):
        embed = discord.Embed(
            title=f"{sender_name} sends duplicates to {recipient_name}",
            description="The following objekts were sent:",
            color=0x00FF00
        )
        max_display_count = 8
        for entry in duplicates_to_send[:max_display_count]:
            embed.add_field(
                name=f"{entry.objekt.member} {entry.objekt.season[0] * int(entry.objekt.season[-1])}{entry.objekt.series}",
                value=f"Rarity: {entry.objekt.rarity}, Class: {entry.objekt.class_}",
                inline=False
            )
        if len(duplicates_to_send) > max_display_count:
            remaining_count = len(duplicates_to_send) - max_display_count
            embed.add_field(name="And ...", value=f"{remaining_count} more objekts were sent.", inline=False)
        return embed

    class ConfirmationView(View):
        def __init__(self, user_id: int):
            super().__init__()
            self.user_id = user_id
            self.value = None

        @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
        async def confirm(self, interaction: discord.Interaction, button: Button):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("You cannot use this button. It is locked to the command caller.", ephemeral=True)
                return
            self.value = True
            await interaction.response.defer()
            self.stop()

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
        async def cancel(self, interaction: discord.Interaction, button: Button):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("You cannot use this button. It is locked to the command caller.", ephemeral=True)
                return
            self.value = False
            await interaction.response.defer()
            self.stop()

    @app_commands.command(name='ping', description="Shows the bot's latency.")
    async def ping_command(self, interaction: Interaction):
        embed = Embed(description=f"My ping is {round(self.bot.latency*1000)}ms")
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="cooldowns", description="Check your current cooldowns.")
    async def cooldowns_command(self, interaction: Interaction):
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        cooldowns = await CooldownModel.filter(user_id=user_id).all()

        if not cooldowns:
            await interaction.followup.send("You currently have no active cooldowns.", ephemeral=True)
            return

        embed = Embed(
            title=f"{interaction.user.name}'s Cooldowns",
            description="Here are your current cooldowns:",
            color=0x00FF00
        )
        for cooldown in cooldowns:
            embed.add_field(
                name=cooldown.command,
                value=f"Time remaining: {await self.format_time_remaining(cooldown.expires_at)}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="chase_check", description="Check your current chase objekt.")
    async def chase_command(self, interaction: Interaction):
        await interaction.response.defer()

        user_id = str(interaction.user.id)

        chase_objekt_data = await PityModel.filter(user_id=user_id).first()

        if not chase_objekt_data:
            await interaction.followup.send("You currently have no chase objekt set.", ephemeral=True)
            return
        
        chase_objekt = await ObjektModel.filter(slug=chase_objekt_data.chase_objekt_slug).first()
        color=int(chase_objekt.background_color.replace("#", ""), 16) if chase_objekt.background_color else 0x00ff00

        embed = Embed(
            title=f"{interaction.user.name}'s Chase Objekt",
            description=f"Your current chase objekt is **{chase_objekt.member} {chase_objekt.season[0] * int(chase_objekt.season[-1])}{chase_objekt.series}**.",
            color=color
        )
        embed.set_image(url=chase_objekt.image_url)

        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="give", description="(Admin Only) Give a specific objekt to a user.")
    @app_commands.describe(
        user="The user to give the objekt to.",
        season="The season of the objekt.",
        member="The member of the objekt.",
        series="The series of the objekt."
    )
    @app_commands.choices(season=SEASON_CHOICES)
    async def give_command(self, interaction: discord.Interaction, user: discord.User, season: str, member: str, series: str):
        await interaction.response.defer()

        if not await self.check_admin_permissions(interaction):
            return
        
        user_id = str(user.id)
        objekt_slug = f"{season}-{member}-{series}".lower()

        # Fetch the objekt
        objekt = await ObjektModel.filter(slug=objekt_slug).first()
        if not objekt:
            await interaction.followup.send("The specified objekt does not exist!", ephemeral=True)
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
        color = int(objekt.background_color.replace("#", ""), 16) if objekt.background_color else 0xFF69B4
        embed = await self.create_embed(
            title=f"{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}",
            description=f"[View Objekt]({objekt.image_url})",
            color=color
        )
        embed.set_image(url=objekt.image_url)

        # Send confirmation
        await interaction.followup.send(
            content=f"**{interaction.user.mention}** has given **{user.mention}** the objekt:\n",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True)
        )
    
    @app_commands.command(name="view", description="View a specific objekt.")
    @app_commands.describe(
        season="The season of the objekt.",
        member="The member of the objekt.",
        series="The series of the objekt.",
        verbose="View all info about an objekt"
    )
    @app_commands.choices(season=SEASON_CHOICES)
    async def view_command(self, interaction: discord.Interaction, season: str, member: str, series: str, verbose: bool | None = False):
        await interaction.response.defer()

        objekt_slug = f"{season}-{member}-{series}".lower()

        # Fetch the objekt
        objekt = await ObjektModel.filter(slug=objekt_slug).first()
        if not objekt:
            await interaction.followup.send("The specified objekt does not exist!", ephemeral=True)
            return

        # Prepare the embed
        rarity_str = RARITY_MAPPING.get(objekt.rarity, "")
        color = int(objekt.background_color.replace("#", ""), 16) if objekt.background_color else 0xFF69B4
        
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
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="series_template", description="View all objekts belonging to a specific series within a specific season.")
    @app_commands.describe(
        season="The season of the series you wish to view.",
        series="The series of objekts you wish to view (ex. 309)."
    )
    @app_commands.choices(season=SEASON_CHOICES)
    async def view_gallery_command(self, interaction: discord.Interaction, season: str, series: str):
        await interaction.response.defer()

        objekts = await ObjektModel.filter(season__iexact=season, series=series).all()

        if not objekts:
            await interaction.followup.send("No objekts found for the specified season and series.", ephemeral=True)
            return

        objekts = sorted(objekts, key=lambda objekt: MEMBER_PRIORITY.get(objekt.member, float('inf')))
        
        num_objekts = len(objekts)
        grid_size = self.determine_grid_size(num_objekts)

        color = int(objekts[0].background_color.replace("#", ""), 16) if objekts and objekts[0].background_color else 0xFF69B4
        
        items_per_page = grid_size[0] * grid_size[1]
        total_pages = (num_objekts + items_per_page - 1) // items_per_page
        current_page = 0

        async def create_collage_for_page(page):
            start = page * items_per_page
            end = start + items_per_page
            page_objekts = objekts[start:end]

            filename, description = await self.generate_collage(
                season, series, page, page_objekts, grid_size
            )
            return filename, description
        
        class PaginationView(View):
            def __init__(self, color):
                super().__init__()
                self.current_page = 0
                self.color = color
            
            async def update_embed(self, interaction: discord.Interaction):
                filename, description = await create_collage_for_page(self.current_page)
                file = discord.File(filename, filename="gallery.png")
                embed = discord.Embed(
                    title=f"tripleS {season[0].capitalize() * int(season[-1])}{series}",
                    description=description,
                    color=self.color
                )
                embed.set_image(url="attachment://gallery.png")
                embed.set_footer(text=f"Page {self.current_page + 1}/{total_pages}")
                await interaction.response.edit_message(embed=embed, view=self, attachments=[file])
            
            @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.gray)
            async def previous_page(self, interaction: discord.Interaction, button: Button):
                self.current_page = (self.current_page - 1) % total_pages
                await self.update_embed(interaction)

            @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.gray)
            async def next_page(self, interaction: discord.Interaction, button: Button):
                self.current_page = (self.current_page + 1) % total_pages
                await self.update_embed(interaction)

        filename, description = await create_collage_for_page(current_page)
        file = discord.File(filename, filename="gallery.png")
        embed = discord.Embed(
            title=f"tripleS {season[0].capitalize() * int(season[-1])}{series}",
            description=description,
            color=color
        )
        embed.set_image(url="attachment://gallery.png")
        embed.set_footer(text=f"Page {current_page + 1}/{total_pages}")
        view = PaginationView(color=color)
        await interaction.followup.send(embed=embed, view=view, file=file)

    @app_commands.command(name="como_leaderboard", description="View the como leaderboard.")
    async def como_leaderboard_command(self, interaction: discord.Interaction):
        await interaction.response.defer()

        leaderboard_data = await EconomyModel.all().order_by("-balance").limit(10).values("id", "balance")

        if not leaderboard_data:
            await interaction.followup.send("No como leaderboard data available.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="GNDSG Slur Gacha Como Leaderboard",
            description="Here are the 10 richest members:",
            color=0xFFD700
        )

        for rank, entry in enumerate(leaderboard_data, start=1):
            user_id = entry["id"]
            balance = entry["balance"]
            user = await self.bot.fetch_user(user_id)
            user_name = user.name if user else "Unknown User"
            embed.add_field(
                name=f"#{rank} {user.name}",
                value=f"Total Como: {balance}",
                inline=False
            )

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="leaderboard", description="View the leaderboard of users with the most collected objekts.")
    @app_commands.describe(
        member="Filter the leaderboard by a specific member.",
        season="Filter the leaderboard by a specific season.",
        mode="Toggle between percent complete or total copies owned."
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Percent Complete", value="percent"),
            app_commands.Choice(name="Copies Owned", value="copies")
        ],
        season=SEASON_CHOICES
    )
    async def leaderboard_command(self, interaction: discord.Interaction, member: str | None = None, season: app_commands.Choice[str] | None = None, mode: app_commands.Choice[str] = None):
        await interaction.response.defer()

        if member and season:
            await interaction.followup.send("You can only filter by one of `member` or `season` at a time.", ephemeral=True)
            return
        
        query = ObjektModel.all()
        if member:
            query = query.filter(member__iexact=member)
        if season:
            query = query.filter(season=season.value)
        
        total_objekts = await query.all()
        total_objekts_ids = [objekt.id for objekt in total_objekts]
        users = await EconomyModel.all()
        
        leaderboard_data = await self.generate_leaderboard_data(users, total_objekts_ids, mode)

        embed_title = self.get_leaderboard_title(mode, member, season)
        
        embed = discord.Embed(title=embed_title, color=0xFFD700)
        self.add_leaderboard_fields(embed, leaderboard_data, mode)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="collection_percentage", description="View your collection completion percentage.")
    @app_commands.describe(user="Indicate who's collection to view. (Leave blank to view your own)",
                           member="View your collection for a specific member. (Cannot be used in conjunction with series filter)",
                           season="View your collection for a specifc season.",
                           class_="View your collection for a specific class of objekts",
                           rarity="View your collection for a specific rarity of objekts",
                           series="View your collection for a specific series of objekts (Requires season filter.)")
    @app_commands.choices(season=SEASON_CHOICES, class_=CLASS_CHOICES, rarity=RARITY_CHOICES)
    async def collection_percentage_command(self, interaction: discord.Interaction, user: discord.User | None = None, member: str | None = None, season: app_commands.Choice[str] | None = None, class_: app_commands.Choice[str] | None = None, rarity: app_commands.Choice[int] | None = None, series: str | None = None):
        await interaction.response.defer()

        if member and series:
            await interaction.followup.send("You cannot filter by both `member` and `series` at the same time. Please choose one.", ephemeral=True)
            return
        
        if series and not season:
            await interaction.followup.send("Filtering by `series` requires specifying the `season` as well.", ephemeral=True)
            return
        
        target = user or interaction.user
        user_id = str(target.id)
        prefix = f"Your ({target})" if not user else f"{user}'s"

        # apply filters
        query = ObjektModel.all()
        if member:
            query = query.filter(member__iexact=member)
        if season:
            query = query.filter(season__iexact=season.value)
        if class_:
            query = query.filter(class___iexact=class_.value)
        if rarity:
            query = query.filter(rarity=rarity.value)
        if series:
            query = query.filter(series=series)
        
        # fetch objekts based on filters
        total_objekts = await query.all()
        total_objekt_ids = [objekt.id for objekt in total_objekts]
        collected_objekts = await CollectionModel.filter(user_id=user_id, objekt__id__in=total_objekt_ids).prefetch_related("objekt")
        collected_ids = {entry.objekt.id for entry in collected_objekts}

        # separate collected from missing
        collected = [objekt for objekt in total_objekts if objekt.id in collected_ids]
        missing = [objekt for objekt in total_objekts if objekt.id not in collected_ids]

        total_count = len(total_objekts)
        collected_count = len(collected)
        collection_percentage = (collected_count / total_count) * 100 if total_count > 0 else 0
        
        title = f"{prefix} Collection"
        if member:
            title += f" ({member})"
        if season:
            title += f" ({season.value})"
        if class_:
            title += f" ({class_.value})"
        if rarity:
            title += f" ({rarity.name})"
        if series:
            title += f" ({series})"
        title += ":"

        items_per_page = 9
        total_pages = max((len(collected) + items_per_page - 1) // items_per_page, (len(missing) + items_per_page - 1) // items_per_page)
        current_page = 0

        def get_page_embed(page):
            start = page * items_per_page
            end = start + items_per_page

            collected_page = collected[start:end]
            missing_page = missing[start:end]

            collected_details = [
                f"{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}" for objekt in collected_page
            ]
            missing_details = [
                f"{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}" for objekt in missing_page
            ]

            embed = discord.Embed(
                title=title,
                description=f"Collection Progress: **{collection_percentage:.2f}%** ({collected_count}/{total_count})",
                color=0x008800
            )
            embed.add_field(name="Collected", value="\n".join(collected_details) or "None", inline=True)
            embed.add_field(name="Missing", value="\n".join(missing_details) or "None", inline=True)
            embed.set_footer(text=f"Page {page + 1}/{total_pages}")

            return embed
        
        class PaginationView(View):
            def __init__(self):
                super().__init__()
                self.current_page = 0

            async def update_embed(self, interaction: discord.Interaction):
                embed = get_page_embed(self.current_page)
                await interaction.response.edit_message(embed=embed, view=self)
            
            @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.gray)
            async def previous_page(self, interaction: discord.Interaction, button: Button):
                self.current_page = (self.current_page - 1) % total_pages
                await self.update_embed(interaction)

            @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.gray)
            async def next_page(self, interaction: discord.Interaction, button: Button):
                self.current_page = (self.current_page + 1) % total_pages
                await self.update_embed(interaction)

        def group_by_season_and_class(objekts):
            grouped = {}
            for objekt in objekts:
                season = objekt.season
                class_ = objekt.class_
                if season not in grouped:
                    grouped[season] = {}
                if class_ not in grouped[season]:
                    grouped[season][class_] = []
                grouped[season][class_].append(objekt)
            return grouped
        
        collected_grouped = group_by_season_and_class(collected)
        missing_grouped = group_by_season_and_class(missing)
        
        embed = discord.Embed(
            title=f"{prefix} Collection Progress",
            description=f"Overall Collection: **{collection_percentage:.2f}%** ({collected_count}/{total_count})",
            color=0x0008800
        )

        for season, classes in collected_grouped.items():
            collected_details = []
            missing_details = []
            for class_, objekts in classes.items():
                collected_details.append(f"**{class_}**: {len(objekts)}")
            for class_, objekts in missing_grouped.get(season, {}).items():
                missing_details.append(f"**{class_}**: {len(objekts)}")
            
            embed.add_field(
                name=f"Collected",
                value="\n".join(collected_details) or "None",
                inline=True
            )
            embed.add_field(
                name=f"Missing",
                value="\n".join(missing_details) or "None",
                inline=True
            )

        embed=get_page_embed(current_page)
        view = PaginationView()
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="compare", description="Compare two users' inventories.")
    @app_commands.describe(
        user1="The first user to compare. (deafaults to command caller)",
        user2="The second user to compare.",
        filter_by_member="Filter the inventory by member. (Leave blank for no filter)",
        filter_by_season="Filter the inventory by season. (Leave blank for no filter)",
        filter_by_class="Filter the inventory by class. (Leave blank for no filter)",
        filter_by_rarity="Filter the inventory by rarity. (Leave blank for no filter)",
        sort_by="The sorting criteria for the inventory.",
        ascending="Sort the inventory in ascending order. (Leave blank to sort in descending order)"
    )
    @app_commands.choices(sort_by=SORT_CHOICES, filter_by_season=SEASON_CHOICES, filter_by_class=CLASS_CHOICES, filter_by_rarity=RARITY_CHOICES)
    async def compare_inventories_command(
        self, interaction: discord.Interaction, user2: discord.User, user1: discord.User | None = None,
        filter_by_member: str | None = None, filter_by_season: app_commands.Choice[str] | None = None,
        filter_by_class: app_commands.Choice[str] | None = None, filter_by_rarity: app_commands.Choice[int] | None = None,
        sort_by: app_commands.Choice[str] | None = None,ascending: bool | None = False
    ):
        await interaction.response.defer()

        user1 = user1 or interaction.user
        user1_id = str(user1.id)
        user2_id = str(user2.id)
        
        # fetch inventory
        query1 = CollectionModel.filter(user_id=user1_id).prefetch_related("objekt")
        query2 = CollectionModel.filter(user_id=user2_id).prefetch_related("objekt")

        # filter
        if filter_by_member:
            query1 = query1.filter(objekt__member__iexact=filter_by_member)
            query2 = query2.filter(objekt__member__iexact=filter_by_member)
        if filter_by_season:
            query1 = query1.filter(objekt__season__iexact=filter_by_season.value)
            query2 = query2.filter(objekt__season__iexact=filter_by_season.value)
        if filter_by_class:
            query1 = query1.filter(objekt__class_=filter_by_class.value)
            query2 = query2.filter(objekt__class_=filter_by_class.value)
        if filter_by_rarity:
            query1 = query1.filter(objekt__rarity=filter_by_rarity.value)
            query2 = query2.filter(objekt__rarity=filter_by_rarity.value)

        user1_inventory = await query1
        user2_inventory = await query2

        def extract_inventory_data(inventory):
            return [
                (
                    entry.objekt.id,
                    entry.objekt.member,
                    entry.objekt.season,
                    entry.objekt.class_,
                    entry.objekt.series,
                    entry.objekt.image_url,
                    entry.objekt.rarity,
                    entry.copies
                )
                for entry in inventory
            ]

        # extract data for sort
        user1_objekts = extract_inventory_data(user1_inventory)
        user2_objekts = extract_inventory_data(user2_inventory)

        # sorting
        sort_by_value = sort_by.value if sort_by else "member"

        def sort_inventory(data, sort_by, ascending):
            sort_key_map = {
                "member": lambda x: x[1].lower(),
                "season": lambda x: x[2].lower(),
                "class": lambda x: x[3].lower(),
                "series": lambda x: x[4].lower(),
                "rarity": lambda x: x[6],
                "copies": lambda x: x[7]
            }
            return sorted(data, key=sort_key_map.get(sort_by, lambda x: x[1].lower()), reverse=not ascending)

        user1_objekts = sort_inventory(user1_objekts, sort_by_value, ascending)
        user2_objekts = sort_inventory(user2_objekts, sort_by_value, ascending)

        # differentials
        user1_only = [objekt for objekt in user1_objekts if objekt[0] not in {obj[0] for obj in user2_objekts}]
        user2_only = [objekt for objekt in user2_objekts if objekt[0] not in {obj[0] for obj in user1_objekts}]

        # pagination
        items_per_page = 9
        total_pages = max(
            (len(user1_only) + items_per_page - 1) // items_per_page,
            (len(user2_only) + items_per_page - 1) // items_per_page,
        )
        current_page = 0

        def get_page_embed(page):
            start = page * items_per_page
            end = start + items_per_page

            user1_page_data = user1_only[start:end]
            user2_page_data = user2_only[start:end]

            user1_field = "\n".join(
                [f"**{obj[1]}** {obj[2][0] * int(obj[2][-1])}{obj[4]} x{obj[7]}" for obj in user1_page_data]
            ) or "None"
            user2_field = "\n".join(
                [f"**{obj[1]}** {obj[2][0] * int(obj[2][-1])}{obj[4]} x{obj[7]}" for obj in user2_page_data]
            ) or "None"

            embed = discord.Embed(
                title="Inventory Comparison",
                description=f"Comparison between {user1.name} and {user2.name}",
                color=0x0000FF
            )
            embed.add_field(name=f"Objekts {user1.name} has but {user2.name} doesn't:", value=user1_field, inline=True)
            embed.add_field(name=f"Objekts {user2.name} has but {user1.name} doesn't:", value=user2_field, inline=True)
            embed.set_footer(text=f"Page {page + 1}/{total_pages}")
            return embed

        class PaginationView(View):
            def __init__(self, user_id: int):
                super().__init__()
                self.current_page = 0
                self.user_id = user_id

            async def update_embed(self, interaction: discord.Interaction):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("You cannot use these buttons. They are locked to the command caller.", ephemeral=True)
                    return
                
                embed = get_page_embed(self.current_page)
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.gray)
            async def previous_page(self, interaction: discord.Interaction, button: Button):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("You cannot use these buttons. They are locked to the command caller.", ephemeral=True)
                    return
                self.current_page = (self.current_page - 1) % total_pages
                await self.update_embed(interaction)

            @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.gray)
            async def next_page(self, interaction: discord.Interaction, button: Button):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("You cannot use these buttons. They are locked to the command caller.", ephemeral=True)
                    return
                self.current_page = (self.current_page + 1) % total_pages
                await self.update_embed(interaction)
            
        embed = get_page_embed(current_page)
        view = PaginationView(user_id=interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="transfer", description="Transfer como to another user.")
    @app_commands.describe(
        recipient="The user to transfer como to.",
        amount="The amount of como to transfer."
    )
    async def transfer_command(self, interaction: discord.Interaction, recipient: discord.User, amount: int):
        await interaction.response.defer()

        sender_id = interaction.user.id
        recipient_id = recipient.id

        if sender_id == recipient_id:
            await interaction.followup.send(f"{interaction.user.mention} can't transfer como to yourself!")
            return
        
        if amount <= 0:
            await interaction.followup.send(f"{interaction.user.mention} must send more than 0 como.")
            return
        
        sender_data, _ = await EconomyModel.get_or_create(id=sender_id)
        recipient_data, _ = await EconomyModel.get_or_create(id=recipient_id)

        if sender_data.balance < amount:
            await interaction.followup.send(f"{interaction.user.mention} doesn't have enough como to complete their send to {recipient.name}! Broke ahh")
            return
        
        async with in_transaction():
            sender_data.balance -= amount
            recipient_data.balance += amount
            await sender_data.save()
            await recipient_data.save()

        embed= await self.create_embed(
            title="Transfer Confirmation",
            description=f"{interaction.user.name} transferred {amount} como to {recipient.name}.",
            fields=[
                ("Sender Balance", f"{interaction.user.name} now has {sender_data.balance} como."),
                ("Recipient Balance", f"{recipient.name} now has {recipient_data.balance} como.")
            ],
            color=0x00ff00
        )

        await interaction.followup.send(f"# Transfer complete\n{interaction.user.mention} transferred **{amount}** como to {recipient.mention}!")

    @app_commands.command(name="give_random_objekts", description="Give a user a random selection of objekts of a specific rarity.")
    @app_commands.describe(
        user="The user to give objekts to.",
        rarity="The rarity of objekts to give.",
        amount="The number of objekts to give."
    )
    @app_commands.choices(rarity=RARITY_CHOICES)
    async def give_random_objekts_command(self, interaction: discord.Interaction, user: discord.User, rarity: app_commands.Choice[int], amount: int):
        await interaction.response.defer()

        if not await self.check_admin_permissions(interaction):
            return
        
        user_id = str(user.id)

        all_objekts = await ObjektModel.filter(rarity=rarity.value).all()
        owned_objekts = await CollectionModel.filter(user_id=user_id).values_list("objekt_id", flat=True)
        unowned_objekts = [objekt for objekt in all_objekts if objekt.id not in owned_objekts]

        selected_objekts = self.select_objekts_to_give(unowned_objekts, all_objekts, amount)

        total_como_reward = self.calculate_como_reward(rarity.value, amount)

        await self.perform_objekt_transaction(user_id, selected_objekts, total_como_reward)
            
        embed = discord.Embed(
            title=f"Gave {amount} {rarity.name} objekts to {user.name}",
            description=f"Added {total_como_reward} como to {user.name}'s balance.",
            color=0x00ff00
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="send_duplicates", description="Send duplicate objekts to another user.")
    @app_commands.describe(recipient="The user to send duplicate objekts to.",
                           member="Filter by member.",
                           season="Filter by season.",
                           rarity="Filter by rarity.",
                           class_="Filter by class.",
                           limit="The maximum number of objekts to send at once. (Default is to send all duplicates.)")
    @app_commands.choices(rarity=RARITY_CHOICES, season=SEASON_CHOICES, class_=CLASS_CHOICES)
    async def send_duplicates_command(
        self, interaction: discord.Interaction, recipient: discord.User, member: str | None = None,
        season: app_commands.Choice[str] | None = None, rarity: app_commands.Choice[int] | None = None,
        class_: app_commands.Choice[str] | None = None, limit: int | None = None
    ):
        await interaction.response.defer()

        sender_id = str(interaction.user.id)
        recipient_id = str(recipient.id)

        if sender_id == recipient_id:
            await interaction.followup.send("You cannot send duplicates to yourself!", ephemeral=True)
            return
        
        sender_inventory = await self.fetch_filtered_inventory(sender_id, member, season, rarity, class_)
        recipient_inventory = await self.fetch_filtered_inventory(recipient_id, member, season, rarity, class_)

        recipient_objekt_ids = {entry.objekt.id for entry in recipient_inventory}
        duplicates_to_send = [
            entry for entry in sender_inventory
            if entry.copies > 1 and entry.objekt.id not in recipient_objekt_ids
        ]

        if not duplicates_to_send:
            await interaction.followup.send("No duplicates found to send!", ephemeral=True)
            return
        
        if limit:
            duplicates_to_send = duplicates_to_send[:limit]
        
        embed = await self.create_confirmation_embed(duplicates_to_send, recipient.name)
        
        view = self.ConfirmationView(user_id=interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)
        await view.wait()

        if view.value is None:
            await interaction.followup.send("Transaction timed out.", ephemeral=True)
            return
        elif not view.value:
            await interaction.followup.send("Transaction cancelled.", ephemeral=True)
            return
        
        await self. perform_duplicates_transaction(sender_id, recipient_id, duplicates_to_send)

        embed = await self.create_success_embed(interaction.user.name, recipient.name, duplicates_to_send)
        await interaction.followup.send(embed=embed)
        
    @app_commands.command(name="give_como", description="(Admin Only) Give a user a specific amount of como.")
    @app_commands.describe(user="The user to give como to.",
                           amount="The amount of como to give.")
    async def give_como_command(self, interaction: discord.Interaction, user: discord.User, amount: int):
        await interaction.response.defer()

        if not await self.check_admin_permissions(interaction):
            return

        if amount <= 0:
            await interaction.followup.send("The amount of como must be greater than 0.", ephemeral=True)
            return

        user_data = await self.update_user_balance(user.id, amount)

        embed = await self.create_embed(
            title="Como Given",
            description=f"**{interaction.user.mention}** has given **{amount} como** to **{user.mention}**.",
            fields=[("New Balance", f"{user.name} now has **{user_data.balance} como**.")]
        )

        await interaction.followup.send(embed=embed)
        
async def setup(bot: Bot) -> None:
    await bot.add_cog(Utility(bot))