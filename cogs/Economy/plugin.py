from __future__ import annotations

import os
import asyncio
import discord
import random
from PIL import Image
from io import BytesIO
import requests
from core import Bot, EconomyModel, ObjektModel, CollectionModel
from tortoise.exceptions import DoesNotExist
from tortoise.transactions import in_transaction
from tortoise.expressions import Q
from tortoise.functions import Function as RandomFunction
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
    
    @app_commands.command(name="balance", description="Show your balance or another user's balance.")
    async def balance_command(self, interaction: discord.Interaction, user: discord.User | None):
        target = user or interaction.user
        data = await self.get_user_data(id=target.id)
        prefix = f"Your ({target})" if not user else f"{user}'s"
        await self.bot.success(
            f"{target} has **{data.balance:.0f} como.**", interaction
        )
    
    @app_commands.command(name="daily", description="Claim a random amount of como daily.")
    @app_commands.checks.cooldown(1, 86400, key=lambda i: (i.user.id,))
    async def daily_command(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        data = await self.get_user_data(id=user_id)
        amount = random.randint(1, 100)
        data.balance += amount
        await data.save()
        await self.bot.success(f"You received **{amount} como.**", interaction)
    @daily_command.error
    async def daily_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            remaining = int(error.retry_after)
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            time_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
            await interaction.response.send_message(
                f"Try again in **{time_str}**.",
                ephemeral=True
            )
        else:
            raise error

    async def rarity_choice(self, class_, weights):
        if not class_:
            return None
        return random.choices(class_, weights=weights)[0]

    async def give_random_objekt(self, user_id: int, season: str | None = None):
        if season == "Atom01":
            class_ = ["Zero", "Welcome", "First", "Special", "Double", "Never"]
            weights = [0.003,0.017,0.25,0.1,0.18,0.45]
            class_choice = await self.rarity_choice(class_, weights)
            ids = await ObjektModel.filter(Q(season=season) | Q(season="GNDSG00"), class_=class_choice).values_list("id", flat=True)
        elif season == "Binary01":
            class_ = ["Welcome", "First", "Special", "Double", "Never"]
            weights = [0.01,0.25,0.08,0.21,0.45]
            class_choice = await self.rarity_choice(class_, weights)
            ids = await ObjektModel.filter(Q(season=season) | Q(season="GNDSG00"), class_=class_choice).values_list("id", flat=True)
        elif season == "Cream01":
            class_ = ["Welcome", "First", "Special", "Double", "Never"]
            weights = [0.012,0.25,0.068,0.22,0.45]
            class_choice = await self.rarity_choice(class_, weights)
            ids = await ObjektModel.filter(Q(season=season) | Q(season="GNDSG00"), class_=class_choice).values_list("id", flat=True)
        elif season == "Divine01":
            class_ = ["Welcome", "First", "Special", "Double", "Premier", "Never"]
            weights = [0.0081,0.25,0.0616,0.23,0.008622,0.45]
            class_choice = await self.rarity_choice(class_, weights)
            ids = await ObjektModel.filter(Q(season=season) | Q(season="GNDSG00"), class_=class_choice).values_list("id", flat=True)
        elif season == "Ever01":
            class_ = ["Welcome", "First", "Special", "Double", "Premier", "Never"]
            weights = [0.008277,0.35,0.049101,0.234,0.008622,0.35]
            class_choice = await self.rarity_choice(class_, weights)
            ids = await ObjektModel.filter(Q(season=season) | Q(season="GNDSG00"), class_=class_choice).values_list("id", flat=True)
        else:
            class_ = ["Zero", "Welcome", "First", "Special", "Double", "Premier", "Never"]
            weights = [0.00036,0.00852,0.35,0.06771,0.22104,0.00237,0.35]
            class_choice = await self.rarity_choice(class_, weights)
            ids = await ObjektModel.filter(class_=class_choice).values_list("id", flat=True)
        
        if not ids:
            return None
        
        random_id = random.choice(ids)

        card = await ObjektModel.get(id=random_id)

        if not card:
            return None
        
        async with in_transaction():
            collection_entry = await CollectionModel.filter(user_id=str(user_id), objekt_id=card.id).first()

            if collection_entry:
                collection_entry.copies += 1
                await collection_entry.save()
            else:
                await CollectionModel.create(user_id=str(user_id), objekt_id=card.id, copies=1)
            #await CollectionModel.create(user_id=str(user_id), card_id=card.id, objekt_id=card.id)

        return card
    
    @app_commands.command(name="spin", description="Collect a random objekt!")
    @app_commands.describe(season="Select a season to spin from (leave blank to spin from all seasons).")
    @app_commands.choices(
        season=[
            app_commands.Choice(name="atom", value="Atom01"),
            app_commands.Choice(name="binary", value="Binary01"),
            app_commands.Choice(name="cream", value="Cream01"),
            app_commands.Choice(name="divine", value="Divine01"),
            app_commands.Choice(name="ever", value="Ever01")
        ]
    )
    @app_commands.checks.cooldown(1,10, key=lambda i: (i.user.id,))
    async def spin_command(self, interaction: discord.Interaction, season: app_commands.Choice[str] | None = None):
        user_id = interaction.user.id
        season_value = season.value if isinstance(season, app_commands.Choice) else season
        card = await self.give_random_objekt(user_id, season=season_value)

        if card:
            embed = discord.Embed(
                title="You received an objekt!",
                color=0xFF69B4
            )
            if card.image_url:
                embed.description = f"[{card.member} {card.season} {card.series}]({card.image_url})"
                embed.set_image(url=card.image_url)
            #embed.set_footer(text=f"You pulled a new [objekt!]({card.image_url})")
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("No objekts found in the database.")
    
    @spin_command.error
    async def spin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            remaining = int(error.retry_after)
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            time_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
            await interaction.response.send_message(
                f"Try again in **{time_str}**.",
                ephemeral=True
            )
        else:
            raise error

    def create_collage(self, image_urls, filename='collage.png', thumb_size=(200, 200), images_per_row=3):
        images = []
        for url in image_urls:
            try:
                response = requests.get(url)
                img = Image.open(BytesIO(response.content))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGBA")
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                else:
                    img = img.convert("RGB")
                img.thumbnail(thumb_size)
                images.append(img)
            except Exception as e:
                print(f"Error loading image from {url}: {e}")
            
        rows = (len(images) + images_per_row - 1) // images_per_row
        collage_width = thumb_size[0] * images_per_row
        collage_height = thumb_size[1] * rows
        collage = Image.new('RGBA', (collage_width, collage_height), (0, 0, 0, 0))

        for index, img in enumerate(images):
            x = (index % images_per_row) * thumb_size[0]
            y = (index // images_per_row) * thumb_size[1]
            collage.paste(img, (x, y))
        
        collage.save(filename, format='PNG')
        return filename

    @app_commands.command(name="inv", description="View your inventory or another user's inventory.")
    @app_commands.describe(
        user="The user whose inventory will be displayed. (Leave blank for your own)",
        sort_by="Sort the inventory by member, season, or class. (Leave blank to sort inventory by date added)"
        descending="Sort the inventory in descending order. (Leave blank to sort in ascending order)"
    )
    @app_commands.choices(
        sort_by=[
            app_commands.Choice(name="member", value="member"),
            app_commands.Choice(name="season", value="season"),
            app_commands.Choice(name="class", value="class")
        ]
    )
    async def inv_command(self, interaction: discord.Interaction, user: discord.User | None = None, sort_by: str | None = None, descending: bool | None = False):
        target = user or interaction.user
        user_id = str(target.id)
        prefix = f"Your ({target})" if not user else f"{user}'s" 

        objekts = await CollectionModel.filter(user_id=user_id).prefetch_related("objekt").order_by('created_at', 'objekt__season', 'objekt__series')
        if not objekts:
            await interaction.send_message(
                f"{prefix} inventory is empty!"
            )
            return
        
        objekt_data = [
            (
                objekt.objekt.id,
                objekt.objekt.member,
                objekt.objekt.season,
                objekt.objekt.class_,
                objekt.objekt.series,
                objekt.objekt.image_url,
                objekt.objekt.rarity,
                objekt.copies
            )
            for objekt in objekts
        ]

        if sort_by:
            sort_by = sort_by.lower()
            if sort_by  == "member":
                objekt_data.sort(key=lambda x: x[1].lower())
            elif sort_by == "season":
                objekt_data.sort(key=lambda x: x[2].lower())
            elif sort_by == "class":
                objekt_data.sort(key=lambda x: x[3].lower())
        
        objekts_per_page = 9
        total_pages = (len(objekt_data) + objekts_per_page - 1) // objekts_per_page
        page = 0

        def get_page_embed(page):
            start = page * objekts_per_page
            end = start + objekts_per_page
            page_objekts = objekt_data[start:end]
            image_urls = [url for _, _, _, _, _, url, _, _ in page_objekts if url]

            collage_path = self.create_collage(image_urls, filename=f'collage_{user_id}.png')

            desc_lines = [
                f"**{member}** {season[0]}{series} x{copies}"
                for _, member, season, _, series, _, _, copies in page_objekts
            ]

            embed = discord.Embed(
                title=f"{prefix} Inventory (Page {page + 1}/{total_pages})",
                description='\n'.join(desc_lines),
                color=0xB19CD9
            )

            return embed, collage_path

        await interaction.response.defer()

        embed, collage_path = get_page_embed(page)
        file = discord.File(collage_path, filename="collage.png")
        embed.set_image(url="attachment://collage.png")
        message = await interaction.followup.send(embed=embed, file=file)

        if total_pages > 1:
            await message.add_reaction("◀️")
            await message.add_reaction("▶️")

            def check(reaction, user):
                return (
                    user == interaction.user and
                    str(reaction.emoji) in ["◀️", "▶️"] and
                    reaction.message.id == message.id
                )
            
            while True:
                try:
                    reaction, _ = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)

                    if str(reaction.emoji) == "▶️" and page < total_pages - 1:
                        page += 1
                    elif str(reaction.emoji) == "◀️" and page > 0:
                        page -= 1
                    elif str(reaction.emoji) == "◀️" and page == 0:
                        page = total_pages - 1
                    elif str(reaction.emoji) == "▶️" and page == total_pages - 1:
                        page = 0
                    else:
                        await message.remove_reaction(reaction.emoji, interaction.user)
                        continue

                    if os.path.exists(collage_path):
                        os.remove(collage_path)

                    embed, collage_path = get_page_embed(page)
                    file = discord.File(collage_path, filename="collage.png")
                    embed.set_image(url="attachment://collage.png")
                    await message.edit(embed=embed, attachments=[file])
                    await message.remove_reaction(reaction.emoji, interaction.user)
                except asyncio.TimeoutError:
                    break
            
            if os.path.exists(collage_path):
                os.remove(collage_path)

    @inv_command.error
    async def spin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            remaining = int(error.retry_after)
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            time_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
            await interaction.response.send_message(
                f"Try again in **{time_str}**.",
                ephemeral=True
            )
        else:
            raise error



    #     if total_pages > 1:
    #         await message.add_reaction("◀️")
    #         await message.add_reaction("▶️")

    #         def check(reaction, user):
    #             return (
    #                 user == interaction.user and
    #                 str(reaction.emoji) in ["◀️", "▶️"] and
    #                 reaction.message.id == message.id
    #             )
            
    #         while True:
    #             try:
    #                 reaction, _ = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)

    #                 if str(reaction.emoji) == "▶️" and page < total_pages - 1:
    #                     page += 1
    #                 elif str(reaction.emoji) == "◀️" and page > 0:
    #                     page -= 1
    #                 else:
    #                     await message.remove_reaction(reaction.emoji, interaction.user)
    #                     continue

    #                 if os.path.exists(collage_path):
    #                     os.remove(collage_path)

    #                 embed, collage_path = get_page_embed(page)
    #                 file = discord.File(collage_path, filename="collage.png")
    #                 embed.set_image(url="attachment://collage.png")
    #                 await message.edit(embed=embed, attachements=[file])
    #                 await message.remove_reaction(reaction.emoji, interaction.user)

    #             except asyncio.TimeoutError:
    #                 break
    #         if os.path.exists(collage_path):
    #             os.remove(collage_path)



    # @app_commands.command(
    #     name="spin", description="Draw a random objekt."
    # )
    # async def spin_command(self, interaction: discord.Interaction, user: discord.User):


async def setup(bot: Bot):
    await bot.add_cog(EconomyPlugin(bot))