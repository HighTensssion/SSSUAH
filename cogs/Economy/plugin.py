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
    
    @app_commands.command(
        name="balance", description="Show your balance or another user's balance."
    )
    async def balance_command(self, interaction: discord.Interaction, user: discord.User):
        target = user or interaction.user
        data = await self.get_user_data(id=target.id)
        prefix = f"Your ({user})" if not user else f"{user}'s"
        await self.bot.success(
            f"{prefix} total balance is: **{data.balance:.2f}**", interaction
        )
    
    async def give_random_objekt(self, user_id: int):
        # card = await ObjektModel.raw("SELECT * FROM objekts ORDER BY RANDOM() LIMIT 1")

        ids = await ObjektModel.all().values_list("id", flat=True)
        if not ids:
            return None
        
        random_id = random.choice(ids)

        card = await ObjektModel.get(id=random_id)

        if not card:
            return None
        
        async with in_transaction():
            await CollectionModel.create(user_id=str(user_id), card_id=card.id, objekt_id=card.id)

        return card
    
    @app_commands.command(
            name="spin", description="Collect a random objekt!"
    )
    @app_commands.checks.cooldown(1,10, key=lambda i: (i.user.id,))
    async def spin_command(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        card = await self.give_random_objekt(user_id)

        if card:
            embed = discord.Embed(
                title=f"{card.member} - {card.season} {card.series}",
                description=f"Group: {card.member}",
                color=0xFF69B4
            )
            if card.image_url:
                embed.set_image(url=card.image_url)
            embed.set_footer(text="You pulled a new objekt!")
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

    # @app_commands.command(
    #     name="inv", description="View your inventory or another user's inventory."
    # )
    # async def inv_command(self, interaction: discord.Interaction, sort_by: str | None = None):
    #     user_id = str(interaction.user.id)

    #     objekts = await CollectionModel.filter(user_id=user_id).prefetch_related("objekt")
    #     if not objekts:
    #         await interaction.response.send_message(
    #             f"{interaction.user.display_name}, your inventory is empty!"
    #         )
    #         return
        
    #     objekt_data = [
    #         (
    #             objekt.objekt.member,
    #             objekt.objekt.season,
    #             objekt.objekt.class_,
    #             objekt.objekt.series,
    #             objekt.objekt.image_url,
    #             objekt.objekt.rarity,
    #             objekt.objekt.copies
    #         )
    #         for objekt in objekts
    #     ]

    #     if sort_by:
    #         sort_by = sort_by.lower()
    #         if sort_by == "member":
    #             objekt_data.sort(key=lambda x: x[0].lower())
    #         elif sort_by == "season":
    #             objekt_data.sort(key=lambda x: x[1].lower())
    #         elif sort_by == "class":
    #             objekt_data.sort(key=lambda x: x[2].lower())
        
    #     per_page = 6
    #     total_pages = (len(objekt_data) + per_page -1) // per_page
    #     page = 0

    #     def get_page_embed(page):
    #         start = page * per_page
    #         end = start + per_page
    #         page_objekts = objekt_data[start:end]
    #         image_urls = [url for _, _, _, _, url, _ in page_objekts if url]

    #         collage_path = create_collage(image_urls, filename=f'collage_{interaction.user.id}.png')

    #         desc_lines = [
    #             f"**{member}** {season} {series} - x{copies}"
    #         ]
    #         embed = discord.Embed(
    #             title=f"{interaction.user.display_name}'s Invetory (Page {page + 1}/{total_pages})",
    #             description='\n'.join(desc_lines),
    #             color=0xB19CD9
    #         )
    #         return embed, collage_path
        
    #     embed, collage_path = get_page_embed(page)
    #     file = discord.File(collage_path, filename="collage.png")
    #     embed.set_image(url="attachment://collage.png")
    #     message = await interaction.response.send_message(embed=embed, file=file)

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