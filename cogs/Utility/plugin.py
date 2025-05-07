from __future__ import annotations

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
from discord import Interaction, app_commands
from discord.ext.commands import is_owner
from discord.ui import View, Button


class Utility(Plugin):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.cache = {}

    @app_commands.command(name='ping', description="Shows the bot's latency.")
    async def ping_command(self, interaction: Interaction):
        embed = Embed(description=f"My ping is {round(self.bot.latency*1000)}ms")
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="cooldowns", description="Check your current cooldowns.")
    async def cooldowns_command(self, interaction: Interaction):
        await interaction.response.defer()

        user_id = str(interaction.user.id)

        # fetch cds
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
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="chase_check", description="Check your current chase objekt.")
    async def chase_command(self, interaction: Interaction):
        await interaction.response.defer()

        user_id = str(interaction.user.id)

        # fetch chase objekt
        chase_objekt_data = await PityModel.filter(user_id=user_id).first()

        if not chase_objekt_data:
            await interaction.followup.send("You currently have no chase objekt set.", ephemeral=True)
            return
        
        chase_objekt = await ObjektModel.filter(slug=chase_objekt_data.chase_objekt_slug).first()

        embed = Embed(
            title=f"{interaction.user.name}'s Chase Objekt",
            description=f"Your current chase objekt is **{chase_objekt.member} {chase_objekt.season[0] * int(chase_objekt.season[-1])}{chase_objekt.series}**.",
            color=int(chase_objekt.background_color.replace("#", ""), 16)
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
    async def give_command(self, interaction: discord.Interaction, user: discord.User, season: str, member: str, series: str):
        await interaction.response.defer()

        if not (await self.bot.is_owner(interaction.user) or interaction.user.guild_permissions.administrator):
            await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
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
        await interaction.followup.send(content=f"**{interaction.user}** has given **{user.mention}** the objekt:\n", embed=embed)
    
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
        await interaction.response.defer()

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
            await interaction.followup.send("The specified objekt does not exist!", ephemeral=True)
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
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="series_template", description="View all objekts belonging to a specific series within a specific season.")
    @app_commands.describe(
        season="The season of the series you wish to view.",
        series="The series of objekts you wish to view (ex. 309)."
    )
    @app_commands.choices(
        season=[
            app_commands.Choice(name="atom01", value="atom01"),
            app_commands.Choice(name="binary01", value="binary01"),
            app_commands.Choice(name="cream01", value="cream01"),
            app_commands.Choice(name="divine01", value="divine01"),
            app_commands.Choice(name="ever01", value="ever01"),
            app_commands.Choice(name="atom02", value="atom02"),
            app_commands.Choice(name="customs", value="gndsg01")
        ]
    )
    async def view_gallery_command(self, interaction: discord.Interaction, season: str, series: str):
        await interaction.response.defer()

        objekts = await ObjektModel.filter(season__iexact=season, series=series).all()

        if not objekts:
            await interaction.followup.send("No objekts found for the specified season and series.", ephemeral=True)
            return
        
        member_priority = {
            "SeoYeon": 1, "Yeonajji": 1.1,
            "HyeRin": 2, "Aekkeangie":  2.1,
            "JiWoo": 3, "Rocketdan": 3.1,
            "ChaeYeon": 4, "Chaengbokdan": 4.1,
            "YooYeon": 5, "Yooenmi": 5.1,
            "SooMin": 6, "Daramdan": 6.1,
            "NaKyoung":7, "Nyangkidan": 7.1,
            "YuBin": 8, "Bambamdan": 8.1,
            "Kaede": 9, "Kaedan": 9.1,
            "DaHyun": 10, "Sodadan": 10.1,
            "Kotone": 11, "Coladan": 11.1,
            "YeonJi": 12, "Quackquackdan": 12.1,
            "Nien": 13, "Honeydan": 13.1,
            "SoHyun": 14, "Nabills": 14.1,
            "Xinyu": 15, "Shinandan": 15.1,
            "Mayu": 16, "Cutiedan": 16.1,
            "Lynn": 17, "Shamedan": 17.1,
            "JooBin": 18, "Jjumeokkongdan": 18.1,
            "HaYeon": 19, "Yukgakdan": 19.1,
            "ShiOn": 20, "Babondan": 20.1,
            "ChaeWon": 21, "Ddallangdan": 21.1,
            "Sullin": 22, "Snowflakes": 22.1,
            "SeoAh": 23, "Haessaldan": 23.1,
            "JiYeon": 24, "Danggeundan": 24.1,
        }

        def custom_sort(objekt):
            return member_priority.get(objekt.member, float('inf'))

        objekts = sorted(objekts, key=custom_sort)
        
        num_objekts = len(objekts)
        if num_objekts == 1:
            grid_size = (1, 1)
        elif num_objekts <= 4:
            grid_size = (2, 2)
        elif num_objekts <= 8:
            grid_size = (4, 2)
        elif num_objekts <= 10:
            grid_size = (5, 2)
        elif num_objekts <= 12:
            grid_size = (4, 3)
        elif num_objekts <= 16:
            grid_size = (4, 4)
        elif num_objekts <= 20:
            grid_size = (5, 4)
        else:
            grid_size = (6, 4)

        if objekts and objekts[0].background_color:
            color = int(objekts[0].background_color.replace("#", ""), 16)
        else:
            color = 0xFF69B4
        
        items_per_page = grid_size[0] * grid_size[1]
        total_pages = (num_objekts + items_per_page - 1) // items_per_page
        current_page = 0

        async def create_collage_for_page(page):
            base_dir = "collage"
            series_dir = os.path.join(base_dir, "series")

            os.makedirs(series_dir, exist_ok=True)

            filename = os.path.join(series_dir, f"collage_{season[0] * int(season[-1])}_{series}_page_{page}.png")

            cache_key = f"{season}_{series}_page_{page}"
            if cache_key in self.cache:
                return self.cache[cache_key]
            
            start = page * items_per_page
            end = start + items_per_page
            page_objekts = objekts[start:end]

            thumb_size = (200, 300)
            gap = 10
            edge_padding = 20

            collage_width = (thumb_size[0] + gap) * grid_size[0] - gap + 2 * edge_padding
            collage_height= (thumb_size[1] + gap) * grid_size[1] - gap + 2 * edge_padding

            if page_objekts and page_objekts[0].background_color:
                base_color = int(page_objekts[0].background_color.replace("#", ""), 16)
                original_r = (base_color >> 16) & 0xFF
                original_g = (base_color >> 8) & 0xFF
                original_b = base_color & 0xFF

                r = int(original_r * 0.8)
                g = int(original_g * 0.8)
                b = int(original_b * 0.8)

                background_color = (r, g, b, 255)
            else:
                background_color = (255, 255, 255, 255)

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
            
            @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.gray)
            async def previous_page(self, interaction: discord.Interaction, button: Button):
                if self.current_page > 0:
                    self.current_page -= 1
                elif self.current_page == 0:
                    self.current_page = total_pages - 1
                await self.update_embed(interaction)

            @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.gray)
            async def next_page(self, interaction: discord.Interaction, button: Button):
                if self.current_page < total_pages - 1:
                    self.current_page += 1
                elif self.current_page == total_pages - 1:
                    self.current_page = 0
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
        season=[
            app_commands.Choice(name="atom01", value="Atom01"),
            app_commands.Choice(name="binary01", value="Binary01"),
            app_commands.Choice(name="cream01", value="Cream01"),
            app_commands.Choice(name="divine01", value="Divine01"),
            app_commands.Choice(name="ever01", value="Ever01"),
            app_commands.Choice(name="atom02", value="Atom02"),
            app_commands.Choice(name="customs", value="GNDSG01")
        ]
    )
    async def leaderboard_command(self, interaction: discord.Interaction, member: str | None = None, season: app_commands.Choice[str] | None = None, mode: app_commands.Choice[str] = None):
        await interaction.response.defer()

        active_filters = sum(bool(x) for x in [member, season])
        if active_filters > 1:
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
                total_count = len(total_objekts)
                percent_complete = (collected_count / total_count) * 100 if total_count > 0 else 0
                leaderboard_data.append((user_id, user_name, percent_complete, collected_count, total_count))
        
        leaderboard_data.sort(key=lambda x: x[2], reverse=True)

        embed_title = "GNDSG Slur Gacha Leaderboard"
        if mode and mode.value == "copies":
            embed_title += f" by Copies"
        else:
            embed_title += f" by Percent Complete"
        if member:
            embed_title += f" ({member}):"
        elif season:
            embed_title += f" ({season.value}):"
        
        embed = discord.Embed(title=embed_title, color=0xFFD700)

        for rank, entry in enumerate(leaderboard_data[:10], start=1):
            if mode and mode.value == "copies":
                user_id, user_name, total_copies = entry
                embed.add_field(name=f"#{rank} {user_name}", value=f"**{total_copies}** copies held", inline=False)
            else:
                user_id, user_name, percent_complete, collected_count, total_count = entry
                embed.add_field(name=f"#{rank} {user_name}", value=f"**({collected_count}/{total_count})** | **{percent_complete:.2f}%** complete", inline=False)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="collection_percentage", description="View your collection completion percentage.")
    @app_commands.describe(user="Indicate who's collection to view. (Leave blank to view your own)",
                           member="View your collection for a specific member. (Cannot be used in conjunction with series filter)",
                           season="View your collection for a specifc season.",
                           class_="View your collection for a specific class of objekts",
                           rarity="View your collection for a specific rarity of objekts",
                           series="View your collection for a specific series of objekts (Requires season filter.)")
    @app_commands.choices(
        season=[
            app_commands.Choice(name="atom01", value="Atom01"),
            app_commands.Choice(name="binary01", value="Binary01"),
            app_commands.Choice(name="cream01", value="Cream01"),
            app_commands.Choice(name="divine01", value="Divine01"),
            app_commands.Choice(name="ever01", value="Ever01"),
            app_commands.Choice(name="atom02", value="Atom02"),
            app_commands.Choice(name="customs", value="GNDSG01")
        ],
        class_=[
            app_commands.Choice(name="customs", value="Never"),
            app_commands.Choice(name="first", value="First"),
            app_commands.Choice(name="double", value="Double"),
            app_commands.Choice(name="special", value="Special"),
            app_commands.Choice(name="welcome", value="Welcome"),
            app_commands.Choice(name="zero", value="Zero"),
            app_commands.Choice(name="premier", value="Premier")
        ],
        rarity=[
            app_commands.Choice(name="Common", value=1),
            app_commands.Choice(name="Uncommon", value=2),
            app_commands.Choice(name="Rare", value=3),
            app_commands.Choice(name="Very Rare", value=4),
            app_commands.Choice(name="Super Rare", value=5),
            app_commands.Choice(name="Ultra Rare", value=6)
        ]
    )
    async def collection_percentage_command(self, interaction: discord.Interaction, user: discord.User | None = None, member: str | None = None, season: app_commands.Choice[str] | None = None, class_: app_commands.Choice[str] | None = None, rarity: app_commands.Choice[int] | None = None, series: str | None = None):
        target = user or interaction.user
        user_id = str(target.id)
        prefix = f"Your ({target})" if not user else f"{user}'s"

        if member and series:
            await interaction.response.send_message("You cannot filter by both `member` and `series` at the same time. Please choose one.", ephemeral=True)
            return
        
        if series and not season:
            await interaction.response.send_message("Filtering by `series` requires specifying the `season` as well.", ephemeral=True)
            return
        
        await interaction.response.defer()

        # apply filters
        query = ObjektModel.all()
        if member:
            query = query.filter(member__iexact=member)
        if season:
            query = query.filter(season=season.value)
        if class_:
            query = query.filter(class_=class_.value)
        if rarity:
            query = query.filter(rarity=rarity.value)
        if series:
            query = query.filter(series=series)
        
        # fetch objekts based on filters
        total_objekts = await query.all()
        total_objekt_ids = [objekt.id for objekt in total_objekts]

        # feth user's filtered collected objekts
        collected_objekts = await CollectionModel.filter(user_id=user_id, objekt__id__in=total_objekt_ids).prefetch_related("objekt")
        collected_ids = {entry.objekt.id for entry in collected_objekts}

        # separate collected from missing
        collected = [objekt for objekt in total_objekts if objekt.id in collected_ids]
        missing = [objekt for objekt in total_objekts if objekt.id not in collected_ids]

        total_count = len(total_objekts)
        collected_count = len(collected)
        if total_count == 0:
            collection_percentage = 0
        else:
            collection_percentage = (collected_count / total_count) * 100
        
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
            embed.add_field(
                name="Collected",
                value="\n".join(collected_details) or "None",
                inline=True
            )
            embed.add_field(
                name="Missing",
                value="\n".join(missing_details) or "None",
                inline=True
            )
            embed.set_footer(text=f"Page {page + 1}/{total_pages}")

            return embed
        
        class PaginationView(View):
            def __init__(self):
                super().__init__()
                self.current_page = 0

            async def update_embed(self, interaction: discord.Interaction):
                embed = get_page_embed(self.current_page)
                await interaction.response.edit_message(embed=embed, view=self)
            
            @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.gray)
            async def previous_page(self, interaction: discord.Interaction, button: Button):
                if self.current_page > 0:
                    self.current_page -= 1
                elif self.current_page == 0:
                    self.current_page = total_pages - 1
                await self.update_embed(interaction)

            @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.gray)
            async def next_page(self, interaction: discord.Interaction, button: Button):
                if self.current_page < total_pages - 1:
                    self.current_page += 1
                elif self.current_page == total_pages - 1:
                    self.current_page = 0
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
        sort_by="The sorting criteria for the inventory.",
        ascending="Sort the inventory in ascending order. (Leave blank to sort in descending order)"
    )
    @app_commands.choices(
        sort_by=[
            app_commands.Choice(name="Member", value="member"),
            app_commands.Choice(name="Season", value="season"),
            app_commands.Choice(name="Class", value="class"),
            app_commands.Choice(name="Series", value="series"),
            app_commands.Choice(name="Rarity", value="rarity"),
            app_commands.Choice(name="Copies", value="copies"),
        ],
        filter_by_season=[
            app_commands.Choice(name="atom01", value="Atom01"),
            app_commands.Choice(name="binary01", value="Binary01"),
            app_commands.Choice(name="cream01", value="Cream01"),
            app_commands.Choice(name="divine01", value="Divine01"),
            app_commands.Choice(name="ever01", value="Ever01"),
            app_commands.Choice(name="atom02", value="Atom02"),
            app_commands.Choice(name="customs", value="GNDSG01")
        ],
        filter_by_class=[
            app_commands.Choice(name="zero", value="Zero"),
            app_commands.Choice(name="welcome", value="Welcome"),
            app_commands.Choice(name="first", value="First"),
            app_commands.Choice(name="special", value="Special"),
            app_commands.Choice(name="double", value="Double"),
            app_commands.Choice(name="customs", value="Never"),
            app_commands.Choice(name="premier", value="Premier")
        ]
    )
    async def compare_inventories_command(self, interaction: discord.Interaction, user2: discord.User, user1: discord.User | None = None, filter_by_member: str | None = None, filter_by_season: app_commands.Choice[str] | None = None, filter_by_class: app_commands.Choice[str] | None = None, sort_by: app_commands.Choice[str] | None = None, ascending: bool | None = False):
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

        user1_inventory = await query1
        user2_inventory = await query2

        # extract data for sort
        user1_objekts = [
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
            for entry in user1_inventory
        ]
        user2_objekts = [
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
            for entry in user2_inventory
        ]

        # sorting
        sort_by_value = sort_by.value if sort_by else "member"

        def sort_inventory(data, sort_by, ascending):
            if sort_by == "member":
                return sorted(data, key=lambda x: x[1].lower(), reverse=not ascending)
            elif sort_by == "season":
                return sorted(data, key=lambda x: x[2].lower(), reverse=not ascending)
            elif sort_by == "class":
                return sorted(data, key=lambda x: x[3].lower(), reverse=not ascending)
            elif sort_by == "series":
                return sorted(data, key=lambda x: x[4].lower(), reverse=not ascending)
            elif sort_by == "rarity":
                return sorted(data, key=lambda x: x[6], reverse=not ascending)
            elif sort_by == "copies":
                return sorted(data, key=lambda x: x[7], reverse=not ascending)
            else:
                return data

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

            @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.gray)
            async def previous_page(self, interaction: discord.Interaction, button: Button):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("You cannot use these buttons. They are locked to the command caller.", ephemeral=True)
                    return
                if self.current_page > 0:
                    self.current_page -= 1
                elif self.current_page == 0:
                    self.current_page = total_pages - 1
                await self.update_embed(interaction)

            @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.gray)
            async def next_page(self, interaction: discord.Interaction, button: Button):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("You cannot use these buttons. They are locked to the command caller.", ephemeral=True)
                    return
                
                if self.current_page < total_pages - 1:
                    self.current_page += 1
                elif self.current_page == total_pages - 1:
                    self.current_page = 0
                await self.update_embed(interaction)
            
        embed = get_page_embed(current_page)
        view = PaginationView(user_id=interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)
        
async def setup(bot: Bot) -> None:
    await bot.add_cog(Utility(bot))