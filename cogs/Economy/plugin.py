from __future__ import annotations

import os
import asyncio
import discord
import random
from PIL import Image
from io import BytesIO
import requests
from core import Bot, EconomyModel, ObjektModel, CollectionModel, CooldownModel, ShopModel, PityModel
from tortoise.exceptions import DoesNotExist
from tortoise.transactions import in_transaction
from tortoise.expressions import Q
from tortoise.functions import Max
from datetime import datetime, timedelta, tzinfo, timezone, time
from .. import Plugin
from discord import app_commands
from discord.ext import tasks
from discord.ui import View, Button

class EconomyPlugin(Plugin):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.refresh_shop_task.start()

    @tasks.loop(time=time(hour=0, minute=0, tzinfo=timezone.utc))
    async def refresh_shop_task(self):
        await self.refresh_shop()
    
    @refresh_shop_task.before_loop
    async def before_refresh_shop_task(self):
        await self.bot.wait_until_ready()

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
    async def daily_command(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        cooldown = await CooldownModel.filter(user_id=user_id, command="daily").first()
        now = datetime.now(tz=timezone.utc)

        if cooldown and cooldown.expires_at > now:
            remaining = cooldown.expires_at - now
            minutes, seconds = divmod(remaining.total_seconds(), 60)
            hours, minutes = divmod(minutes, 60)
            await interaction.response.send_message(
                f"You are on cooldown! Try again in {int(hours)}h{int(minutes)}m.",
                ephemeral=True
            )
            return
        
        # give como
        data = await self.get_user_data(id=user_id)
        amount = random.randint(1, 100)
        data.balance += amount
        await data.save()

        # give objekt
        rarity = random.choice([1,2])
        objekt_ids = await ObjektModel.filter(rarity=rarity).values_list("id", flat=True)

        if not objekt_ids:
            await interaction.response.send_message(f"You received **{amount}** como but no objekts of rarity {rarity} are available in the database.", ephemeral=True)
            return
    
        random_objekt_id = random.choice(objekt_ids)
        objekt = await ObjektModel.get(id=random_objekt_id)

        objekt = await ObjektModel.get(id=random_objekt_id)
        if objekt.background_color:
            color = int(objekt.background_color.replace("#", ""), 16)
        else:
            color=0xFF69B4

        async with in_transaction():
            collection_entry = await CollectionModel.filter(user_id=str(user_id), objekt_id=objekt.id).first()

            if collection_entry:
                collection_entry.copies += 1
                await collection_entry.save()
            else:
                await CollectionModel.create(user_id=str(user_id), objekt_id=objekt.id, copies=1)

        expires_at = now + timedelta(hours=24)
        if cooldown:
            cooldown.expires_at = expires_at
            await cooldown.save()
        else:
            await CooldownModel.create(user_id=user_id, command="daily", expires_at=expires_at)

        embed = discord.Embed(
            title="Daily Reward!",
            description=f"You received **{amount} como** and **{objekt.member} {objekt.season[0]}{objekt.series}**!",
            color=color
        )
        if objekt.image_url:
            embed.set_image(url=objekt.image_url)
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="weekly", description="Claim 500 como and a rare objekt weekly.")
    async def weekly_command(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        cooldown = await CooldownModel.filter(user_id=user_id, command="weekly").first()
        now = datetime.now(tz=timezone.utc)

        if cooldown and cooldown.expires_at > now:
            remaining = cooldown.expires_at - now
            minutes, seconds = divmod(remaining.total_seconds(), 60)
            hours, minutes = divmod(minutes, 60)
            days, hours = divmod(hours, 24)
            await interaction.response.send_message(
                f"You are on cooldown! Try again in {int(days)}d {int(hours)}h {int(minutes)}m.",
                ephemeral=True
            )
            return
        
        # give como
        data = await self.get_user_data(id=user_id)
        como_amount = 500
        data.balance += como_amount
        await data.save()

        # give objekt
        rarity_choices = [4, 5, 6]
        rarity_weights = [0.6, 0.3, 0.1]
        chosen_rarity = random.choices(rarity_choices, weights=rarity_weights, k=1)[0]

        objekt_ids = await ObjektModel.filter(rarity=chosen_rarity).values_list("id", flat=True)

        if not objekt_ids:
            await interaction.response.send_message(
                f"You received **{como_amount} como**, but no objekts of rarity {chosen_rarity} are available in the database.",
                ephemeral=True
            )
            return
        
        random_objekt_id = random.choice(objekt_ids)
        objekt = await ObjektModel.get(id=random_objekt_id)
        if objekt.background_color:
            color = int(objekt.background_color.replace("#", ""), 16)
        else:
            color=0xFF69B4

        async with in_transaction():
            collection_entry = await CollectionModel.filter(user_id=str(user_id), objekt_id=objekt.id).first()

            if collection_entry:
                collection_entry.copies += 1
                await collection_entry.save()
            else:
                await CollectionModel.filter(user_id=str(user_id), objekt_id=objekt.id, copies=1)

            # cooldown set
            expires_at = now + timedelta(days=7)
            if cooldown:
                cooldown.expires_at = expires_at
                await cooldown.save()
            else:
                await CooldownModel.create(user_id=user_id, command="weekly", expires_at=expires_at)
            
            # response
            embed = discord.Embed(
                title="Weekly",
                description=f"You received **{como_amount} como** and **{objekt.member} {objekt.season[0]}{objekt.series}**!",
                color=color
            )
            if objekt.image_url:
                embed.set_image(url=objekt.image_url)
            
            await interaction.response.send_message(embed=embed)

    async def rarity_choice(self, rarity, weights):
        if not rarity:
            return None
        return random.choices(rarity, weights=weights)[0]

    async def give_random_objekt(self, user_id: int, banner: str | None = None, pity_entry: PityModel | None = None):
        rarity = [6,5,4,3,2,1]
        weights = [0.003,0.03,0.067,0.1,0.2,0.6]
        rarity_choice = await self.rarity_choice(rarity, weights)
        
        # handle banners
        if banner == "rateup":
            rarity = [7, 1]
            weights = [0.4, 0.6]
            rarity_choice = await self.rarity_choice(rarity, weights)
            
            if rarity_choice == 1:
                sub_rarity = ["Ever01", "GNDSG00"]
                sub_weights = [0.3, 0.7]
                season_choice = await self.rarity_choice(sub_rarity, sub_weights)
                ids = await ObjektModel.filter(season=season_choice, rarity=rarity_choice).values_list("id", flat = True)
            else:
                ids = await ObjektModel.filter(Q(season="Ever01"), rarity=rarity_choice).values_list("id", flat=True)
        elif banner:
            if rarity_choice == 1:
                sub_rarity = [banner, "GNDSG00"]
                sub_weights = [0.3, 0.7]
                season_choice = await self.rarity_choice(sub_rarity, sub_weights)
                ids = await ObjektModel.filter(season=season_choice, rarity=rarity_choice).values_list("id", flat = True)
            else:
                ids = await ObjektModel.filter(season=banner, rarity=rarity_choice).values_list("id", flat=True)
        else:
            ids = await ObjektModel.filter(rarity=rarity_choice).values_list("id", flat=True)
        
        if not ids:
            return None, None
        
        # handle pity
        if pity_entry:
            if pity_entry.chase_objekt_slug:
                # check for early pity
                chase_objekt = await ObjektModel.filter(slug=pity_entry.chase_objekt_slug).first()
                if chase_objekt and chase_objekt.id in ids: # chase objekt is obtainable naturally
                    random_id = random.choice(ids)
                    card = await ObjektModel.get(id=random_id)

                    if card.id == chase_objekt.id: # chase obtained naturally before pity
                        pity_taken = pity_entry.chase_pity_count
                        pity_entry.chase_pity_count = 0
                        pity_entry.chase_objekt_slug = None
                        pity_entry.pity_count = 0 # general pity reset
                        await pity_entry.save()

                        async with in_transaction():
                            collection_entry = await CollectionModel.filter(user_id=user_id, objekt_id=card.id).first()
                            if collection_entry:
                                collection_entry.copies += 1
                                await collection_entry.save()
                            else:
                                await CollectionModel.create(user_id=user_id, objekt_id=card.id, copies=1)
                        return card, pity_taken
                    
                pity_entry.chase_pity_count += 1
                if pity_entry.chase_pity_count >= 250:
                    if chase_objekt:
                        # pity reset
                        pity_taken = pity_entry.chase_pity_count
                        pity_entry.chase_pity_count = 0
                        pity_entry.chase_objekt_slug = None
                        pity_entry.pity_count = 0 # reset general pity
                        await pity_entry.save()

                        async with in_transaction():
                            collection_entry = await CollectionModel.filter(user_id=user_id, objekt_id=chase_objekt.id).first()
                            if collection_entry:
                                collection_entry.copies += 1
                                await collection_entry.save()
                            else:
                                await CollectionModel.create(user_id=user_id, objekt_id=chase_objekt.id, copies=1)
                        return chase_objekt, pity_taken
                
            # general pity logic
            low_rarities = [1, 2, 3]
            if rarity_choice in low_rarities:
                pity_entry.pity_count += 1
            else:
                pity_entry.pity_count = 0
                
            if pity_entry.pity_count >= 80:
                pity_entry.pity_count = 0
                owned_ids = await CollectionModel.filter(user_id=user_id).values_list("objekt_id", flat=True)
                
                # apply season filtering if banner is specified
                if banner:
                    higher_rarity_cards = await ObjektModel.filter(rarity__gte=4, season=banner).exclude(id__in=owned_ids).values_list("id", flat=True)
                else:
                    higher_rarity_cards = await ObjektModel.filter(rarity__gte=4).exclude(id__in=owned_ids).values_list("id", flat=True)

                if higher_rarity_cards:
                    pity_card_id = random.choice(higher_rarity_cards)
                    pity_card = await ObjektModel.get(id=pity_card_id)

                    async with in_transaction():
                        collection_entry = await CollectionModel.filter(user_id=user_id, objekt_id=pity_card.id).first()
                        if collection_entry:
                            collection_entry.copies += 1
                            await collection_entry.save()
                        else:
                            await CollectionModel.create(user_id=user_id, objekt_id=pity_card.id, copies=1)
                    await pity_entry.save()
                    return pity_card, None
            await pity_entry.save()

        # random selection
        random_id = random.choice(ids)
        card = await ObjektModel.get(id=random_id)

        if not card:
            return None, None
        
        async with in_transaction():
            collection_entry = await CollectionModel.filter(user_id=str(user_id), objekt_id=card.id).first()

            if collection_entry:
                collection_entry.copies += 1
                await collection_entry.save()
            else:
                await CollectionModel.create(user_id=str(user_id), objekt_id=card.id, copies=1)

        return card, None
    
    @app_commands.command(name="set_chase", description="Set a chase objekt, which you will be guaranteed to receive within 250 spins.")
    @app_commands.describe(season="The season which your chase objekt is in.",
                           member="The member whose objekt you wish to chase. (Ex. Nien, Honeydan)",
                           series="The series of your desired chase objekt. (Ex. 000, 309, 901)")
    @app_commands.choices(
        season=[
            app_commands.Choice(name="atom01", value="atom01"),
            app_commands.Choice(name="binary01", value="binary01"),
            app_commands.Choice(name="cream01", value="cream01"),
            app_commands.Choice(name="divine01", value="divine01"),
            app_commands.Choice(name="ever01", value="ever01"),
            app_commands.Choice(name="customs", value="gndsg00")
        ]
    )
    async def set_chase_command(self, interaction: discord.Interaction, season: str, member: str, series: int):
        user_id = str(interaction.user.id)
        objekt_slug = f"{season}-{member}-{series}".lower()

        # validate slug
        objekt = await ObjektModel.filter(slug=objekt_slug).first()
        if not objekt:
            await interaction.response.send_message("The specified objekt slug does not exist!", ephemeral=True)
            return
        
        # get or create the user's pity entry
        pity_entry, _ = await PityModel.get_or_create(user_id=user_id)

        # update chase objekt
        pity_entry.chase_objekt_slug = objekt_slug
        pity_entry.chase_pity_count = 0
        await pity_entry.save()

        await interaction.response.send_message(
            f"Your chase objekt has been set to **{objekt.member} {objekt.season[0]}{objekt.series}**!"
        )
    
    @app_commands.command(name="spin", description="Collect a random objekt!")
    @app_commands.describe(banner="Select a banner to spin from (leave blank to spin all seasons).")
    @app_commands.choices(
        banner=[
            app_commands.Choice(name="atom", value="Atom01"),
            app_commands.Choice(name="binary", value="Binary01"),
            app_commands.Choice(name="cream", value="Cream01"),
            app_commands.Choice(name="divine", value="Divine01"),
            app_commands.Choice(name="ever", value="Ever01"),
            app_commands.Choice(name="rateup", value="rateup")
        ]
    )
    @app_commands.checks.cooldown(1,10, key=lambda i: (i.user.id,))
    async def spin_command(self, interaction: discord.Interaction, banner: app_commands.Choice[str] | None = None):
        user_id = interaction.user.id
        banner_value = banner.value if isinstance(banner, app_commands.Choice) else banner

        # user's pity counter
        pity_entry, _ = await PityModel.get_or_create(user_id=user_id)

        # roll
        card, pity_taken = await self.give_random_objekt(user_id, banner=banner_value, pity_entry=pity_entry)

        if not card:
            await interaction.response.send_message("No objekts found in the database.")
            return

        if card.background_color:
            color = int(card.background_color.replace("#", ""), 16)
        else:
            color=0xFF69B4
        
        collection_entry = await CollectionModel.filter(user_id=str(user_id), objekt_id=card.id).first()        
        if collection_entry and collection_entry.copies > 1:
            copies_message = f"You now have {collection_entry.copies} copies of this objekt!"
        else:
            copies_message = "Congrats on your new objekt!"

        rarity_mapping = {
            1: "n ",
            2: "n ",
            3: " Rare ",
            4: " Very Rare ",
            5: " Super Rare ",
            6: "n Ultra Rare ",
            7: "n "
        }

        rarity_str = rarity_mapping.get(card.rarity, "n ")

        # check if chase target is reached
        if pity_taken:
            # target reached
            embed = discord.Embed(
                    title=f"Congratulations, {interaction.user}, after {pity_taken} spins, your chase ended!",
                    color=color
            )
            if card.image_url:
                embed.description = f"[{card.member} {card.season[0]}{card.series}]({card.image_url})"
                embed.set_image(url=card.image_url)
        
            embed.set_footer(text="Don't forget to set a new chase objekt with /set_chase!")
        else:
            embed = discord.Embed(
                title=f"You ({interaction.user}) received a{rarity_str}objekt!",
                color=color
            )
            if card.image_url:
                embed.description = f"[{card.member} {card.season[0]}{card.series}]({card.image_url})"
                embed.set_image(url=card.image_url)
            
            general_pity = pity_entry.pity_count if pity_entry else 0
            chase_pity = pity_entry.chase_pity_count if pity_entry else 0
            footer_text = f"{copies_message}\nGeneral Pity: {general_pity} | Chase Pity: {chase_pity}/250"
            embed.set_footer(text=footer_text)
            
        await interaction.response.send_message(embed=embed)
    
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
        sort_by="Sort the inventory by member, season, class, series, amount owned, or rarity. (Leave blank to sort inventory by date added)",
        filter_by_member="Filter the inventory by member. (Leave blank for no filter)",
        filter_by_season="Filter the inventory by season. (Leave blank for no filter)",
        filter_by_class="Filter the inventory by class. (Leave blank for no filter)",
        ascending="Sort the inventory in ascending order. (Leave blank to sort in descending order)"
    )
    @app_commands.choices(
        sort_by=[
            app_commands.Choice(name="member", value="member"),
            app_commands.Choice(name="season", value="season"),
            app_commands.Choice(name="class", value="class"),
            app_commands.Choice(name="series", value="series"),
            app_commands.Choice(name="copies", value="copies"),
            app_commands.Choice(name="rarity", value="rarity")
        ],
        filter_by_member=[
            app_commands.Choice(name="Chaewon", value="ChaeWon"),
            app_commands.Choice(name="Chaeyeon", value="ChaeYeon"),
            app_commands.Choice(name="Dahyun", value="DaHyun"),
            app_commands.Choice(name="Hayeon", value="HaYeon"),
            app_commands.Choice(name="Hyerin", value="HyeRin"),
            app_commands.Choice(name="Jiwoo", value="JiWoo"),
            app_commands.Choice(name="Jiyeon", value="JiYeon"),
            app_commands.Choice(name="Joobin", value="JooBin"),
            app_commands.Choice(name="Kaede", value="Kaede"),
            app_commands.Choice(name="Kotone", value="Kotone"),
            app_commands.Choice(name="Lynn", value="Lynn"),
            app_commands.Choice(name="Mayu", value="Mayu"),
            app_commands.Choice(name="Nakyoung", value="NaKyoung"),
            app_commands.Choice(name="Nien", value="Nien"),
            app_commands.Choice(name="Seoah", value="SeoAh"),
            app_commands.Choice(name="Seoyeon", value="SeoYeon"),
            app_commands.Choice(name="Shion", value="ShiOn"),
            app_commands.Choice(name="Sohyun", value="SoHyun"),
            app_commands.Choice(name="Soomin", value="SooMin"),
            app_commands.Choice(name="Sullin", value="Sullin"),
            app_commands.Choice(name="Xinyu", value="Xinyu"),
            app_commands.Choice(name="Yeonji", value="YeonJi"),
            app_commands.Choice(name="Yooyeon", value="YooYeon"),
            app_commands.Choice(name="Yubin", value="YuBin")
        ],
        filter_by_season=[
            app_commands.Choice(name="atom", value="Atom01"),
            app_commands.Choice(name="binary", value="Binary01"),
            app_commands.Choice(name="cream", value="Cream01"),
            app_commands.Choice(name="divine", value="Divine01"),
            app_commands.Choice(name="ever", value="Ever01"),
            app_commands.Choice(name="customs", value="GNDSG00")
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
    async def inv_command(self,
                          interaction: discord.Interaction,
                          user: discord.User | None = None,
                          sort_by: str | None = None,
                          filter_by_member: str | None = None,
                          filter_by_season: str | None = None,
                          filter_by_class: str | None = None,
                          ascending: bool | None = False
                          ):
        target = user or interaction.user
        user_id = str(target.id)
        prefix = f"Your ({target})" if not user else f"{user}'s" 

        query = CollectionModel.filter(user_id=user_id).prefetch_related("objekt")

        if filter_by_member:
            query = query.filter(objekt__member=filter_by_member)
        if filter_by_season:
            query = query.filter(objekt__season=filter_by_season)
        if filter_by_class:
            query = query.filter(objekt__class_=filter_by_class)

        if ascending:
            query = query.order_by('updated_at')
        else:
            query = query.order_by('-updated_at')

        objekts = await query
        
        if not objekts:
            await interaction.response.send_message(
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
            if ascending:
                if sort_by  == "member":
                    objekt_data.sort(key=lambda x: x[1].lower())
                elif sort_by == "season":
                    objekt_data.sort(key=lambda x: x[2].lower())
                elif sort_by == "class" or sort_by == "series":
                    objekt_data.sort(key=lambda x: x[4].lower())
                elif sort_by == "rarity":
                    objekt_data.sort(key=lambda x: x[6])
                elif sort_by == "copies":
                    objekt_data.sort(key=lambda x: x[7])
                
            else:
                if sort_by  == "member":
                    objekt_data.sort(key=lambda x: x[1].lower(), reverse=True)
                elif sort_by == "season":
                    objekt_data.sort(key=lambda x: x[2].lower(), reverse=True)
                elif sort_by == "class" or sort_by == "series":
                    objekt_data.sort(key=lambda x: x[4].lower(), reverse=True)
                elif sort_by == "rarity":
                    objekt_data.sort(key=lambda x: x[6], reverse=True)
                elif sort_by == "copies":
                    objekt_data.sort(key=lambda x: x[7], reverse=True)
        
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
        
    @app_commands.command(name="rob", description="Steal an objekt from another user.")
    @app_commands.describe(target="The user to rob.")
    async def rob_command(self, interaction: discord.Interaction, target: discord.User):
        user_id = str(interaction.user.id)
        target_id = str(target.id)

        if target_id == user_id:
            await interaction.response.send_message("You can't rob yourself!")
            return
        
        cooldown = await CooldownModel.filter(user_id=user_id, command="rob").first()
        now = datetime.now(tz=timezone.utc)

        if cooldown and cooldown.expires_at > now:
            remaining = cooldown.expires_at - now
            minutes, seconds = divmod(remaining.total_seconds(), 60)
            hours, minutes = divmod(minutes, 60)
            await interaction.response.send_message(
                f"You are on cooldown! Try again in {int(hours)}h {int(minutes)}m {int(seconds)}s.",
                ephemeral=True
            )
            return

        target_inventory = await CollectionModel.filter(user_id=target_id).prefetch_related("objekt")

        if not target_inventory:
            await interaction.response.send_message(f"{target} has nothing to rob!")
            return
        
        stolen_objekt = random.choice(target_inventory)

        async with in_transaction():
            if stolen_objekt.copies > 1:
                stolen_objekt.copies -= 1
                await stolen_objekt.save()
            else:
                await stolen_objekt.delete()

            user_entry = await CollectionModel.filter(user_id=user_id, objekt_id=stolen_objekt.objekt.id).first()

            if user_entry:
                user_entry.copies += 1
                await user_entry.save()
            else:
                await CollectionModel.create(user_id=user_id, objekt=stolen_objekt.objekt, copies=1)
        
        expires_at = now + timedelta(hours=6)
        if cooldown:
            cooldown.expires_at = expires_at
            await cooldown.save()
        else:
            await CooldownModel.create(user_id=user_id, command="rob", expires_at=expires_at)

        await interaction.response.send_message(
            f"{target.mention}, you have been robbed!\n"
            f"{interaction.user} stole [{stolen_objekt.objekt.member} {stolen_objekt.objekt.season[0]}{stolen_objekt.objekt.series}]({stolen_objekt.objekt.image_url}) from you!"
        )

    @app_commands.command(name="send", description="Send an objekt to another user.")
    @app_commands.describe(
        recipient="The user to send the objekt to.",
        season="The season that the objekt you wish to send belongs to.",
        member="The member whose objekt you wish to send. (Ex. Yooyeon, Nyangkidan)",
        series="The series of the objekt you wish to send. (Ex. 000, 100, 309)"
    )
    @app_commands.choices(
        season=[
            app_commands.Choice(name="atom01", value="atom01"),
            app_commands.Choice(name="binary01", value="binary01"),
            app_commands.Choice(name="cream01", value="cream01"),
            app_commands.Choice(name="divine01", value="divine01"),
            app_commands.Choice(name="ever01", value="ever01"),
            app_commands.Choice(name="customs", value="gndsg00")
        ]
    )
    async def send_objekt_command(self, interaction:discord.Interaction, recipient: discord.User, season: str, member: str, series: int):
        sender_id = str(interaction.user.id)
        recipient_id = str(recipient.id)
        objekt_slug = f"{season}-{member}-{series}".lower()

        if sender_id == recipient_id:
            await interaction.response.send_message("You can't send an objekt to yourself!", ephemeral=True)
            return
        
        objekt = await ObjektModel.filter(slug=objekt_slug).first()
        if not objekt:
            await interaction.response.send_message("Objekt not found!", ephemeral=True)
            return

        async with in_transaction():
            sender_entry = await CollectionModel.filter(user_id=sender_id, objekt_id=objekt.id).first()

            if not sender_entry or sender_entry.copies < 1:
                await interaction.response.send_message("You don't have that objekt!", ephemeral=True)
                return
            
            sender_entry.copies -= 1
            if sender_entry.copies == 0:
                await sender_entry.delete()
            else:
                await sender_entry.save()
            
            recipient_entry = await CollectionModel.filter(user_id=recipient_id, objekt_id=objekt.id).first()

            if recipient_entry:
                recipient_entry.copies += 1
                await recipient_entry.save()
            else:
                await CollectionModel.create(user_id=recipient_id, objekt_id=objekt.id, copies=1)
            
        objekt = await ObjektModel.get(slug=objekt_slug)

        if objekt:
            if objekt.background_color:
                color = int(objekt.background_color.replace("#", ""), 16)
            else:
                color=0xFF69B4

            embed = discord.Embed(
                title=f"{interaction.user} sends an objekt to {recipient}!",
                description=f"[{objekt.member} {objekt.season[0]}{objekt.series}]({objekt.image_url})",
                color=color
            )
            embed.set_image(url=objekt.image_url)

            await interaction.response.send_message(embed=embed)

            await interaction.followup.send(
                f"{interaction.user.mention} successfully sent **{objekt.member} {objekt.season[0]}{objekt.series}** to {recipient.mention}!"
            )
        else:
            await interaction.response.send_message("No objekts found in the database.")
    
    def create_sell_callback(self, user_id: str, rarity: int, leave: int):
        async def callback(interaction: discord.Interaction):
            # inventory
            collection_entries = await CollectionModel.filter(user_id=user_id, objekt__rarity=rarity).prefetch_related("objekt")
            if not collection_entries:
                await interaction.response.send_message(f"You have no extra objekts of rarity {rarity} to sell!", ephemeral=True)
                return
            
            total_sold = 0
            total_value = 0
            rarity_values = {
                1: 2,
                2: 10,
                3: 30,
                4: 70,
                5: 150,
                6: 400,
                7: 10,
            }

            async with in_transaction():
                for entry in collection_entries:
                    if entry.copies > leave:
                        sell_count = entry.copies - leave
                        sale_value = rarity_values.get(rarity, 0) * sell_count
                        total_sold += sell_count
                        total_value += sale_value

                        entry.copies = leave
                        if entry.copies == 0:
                            await entry.delete()
                        else: 
                            await entry.save()

                user_data = await self.get_user_data(id=int(user_id))
                user_data.balance += total_value
                await user_data.save()
            
            await interaction.response.send_message(
                f"{interaction.user.name} sold **{total_sold} objekts** of rarity {rarity} for **{total_value}** como."
            )
        
        return callback

    @app_commands.command(name="sell", description="Sell your duplicate objekts for como. (Do not sell rarity 7 dupes, as they may go up in value)")
    @app_commands.describe(
        leave="The number of duplicates to leave in your inventory (only for bulk selling)."
    )
    async def sell_objekt_command(self, interaction: discord.Interaction, leave: int = 1):
        user_id = str(interaction.user.id)

        # fetch inventory
        collection_entries = await CollectionModel.filter(user_id=user_id).prefetch_related("objekt")
        rarity_summary = {}
        for entry in collection_entries:
            rarity = entry.objekt.rarity
            if rarity not in rarity_summary:
                rarity_summary[rarity] = {"unique": 0, "dupes": 0}
            rarity_summary[rarity]["unique"] += 1
            if entry.copies > leave:
                rarity_summary[rarity]["dupes"] += entry.copies - leave
        
        embed = discord.Embed(
            title=f"{interaction.user.name}'s Inventory Overview",
            description="Here is an overview of your inventory by rarity tier:",
            color=0xFFFFFF
        )
        for rarity, counts in sorted(rarity_summary.items()):
            embed.add_field(
                name=f"Rarity {rarity}",
                value=f"Unique: {counts['unique']} | Dupes above sell limit: {counts['dupes']}",
                inline=False
            )
        
        view = View()
        for rarity in sorted(rarity_summary.keys()):
            button = Button(label=f"Sell Rarity {rarity}", style=discord.ButtonStyle.blurple)
            button.callback = self.create_sell_callback(user_id, rarity, leave)
            view.add_item(button)
        
        await interaction.response.send_message(embed=embed, view=view)
        
    async def refresh_shop(self):
        now = datetime.now(tz=timezone.utc)
        midnight = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
            
        await ShopModel.all().delete()

        users = await EconomyModel.all()

        buy_values = {
            1: 5,
            2: 15,
            3: 35,
            4: 75,
            5: 200,
            6: 1000,
        }
        rarity_tiers = [1, 2, 3, 4, 5, 6]

        for user in users:
            user_id = user.id
            items = []
            for rarity in rarity_tiers:
                objekts = await ObjektModel.filter(rarity=rarity).all()

                if objekts:
                    objekt = random.choice(objekts)
                    price = buy_values.get(objekt.rarity, 0)
                    items.append(ShopModel(user_id=user_id, objekt=objekt, price=price))

            await ShopModel.bulk_create(items)

    def create_purchase_callback(self, shop_item, user):
        async def callback(interaction:discord.Interaction):
            if interaction.user != user:
                await interaction.response.send_message("Open your own shop to purchase!", ephemeral=True)
                return

            user_data = await self.get_user_data(id=user.id)

            if user_data.balance < shop_item.price:
                await interaction.response.send_message("You don't have enough como!", ephemeral=True)
                return
            
            user_data.balance -= shop_item.price
            await user_data.save()

            collection_entry = await CollectionModel.filter(user_id=str(user.id), objekt_id=shop_item.objekt.id).first()
            if collection_entry:
                collection_entry.copies += 1
                await collection_entry.save()
            else:
                await CollectionModel.create(user_id=str(user.id), objekt_id=shop_item.objekt.id, copies=1)
            
            await interaction.response.send_message(
                f"{user.mention} successfully purchased **[{shop_item.objekt.member} {shop_item.objekt.season[0]}{shop_item.objekt.series}]({shop_item.objekt.image_url})** for **{shop_item.price}** como!"
            )
        
        return callback

    @app_commands.command(name="shop", description="View the shop.")
    async def shop_command(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        shop_items = await ShopModel.filter(user_id=user_id).prefetch_related("objekt")

        if not shop_items:
            await interaction.response.send_message("Your shop is currently empty. Please wait for the next refresh!")
            return
        
        embed = discord.Embed(title=f"{interaction.user.name}'s Shop", color=0x000000)
        buttons = []
        for index, item in enumerate(shop_items):
            embed.add_field(
                name=f"{item.objekt.member} {item.objekt.season[0]}{item.objekt.series}",
                value=f"Rarity: {item.objekt.rarity}\nPrice: {item.price} como\n[View Objekt]({item.objekt.image_url})\n\n",
                inline=True
            )

            button = Button(label=f"Buy obj. {index + 1}", style=discord.ButtonStyle.blurple)
            button.callback = self.create_purchase_callback(item, interaction.user)
            buttons.append(button)
        
        view = View()
        for index, button in enumerate(buttons):
            button.row = index // 3
            view.add_item(button)
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="slots", description="Bet your como and spin the slot machine!")
    @app_commands.describe(
        bet="The amount of como to bet on the slot machine."
    )
    @app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id,))
    async def slots_command(self, interaction: discord.Interaction, bet: int):
        user_id = interaction.user.id

        # check valid bet
        if bet <= 0:
            await interaction.response.send_message("Your bet must be greater than 0!", ephemeral=True)
            return
        
        user_data = await self.get_user_data(id=user_id)

        # check bet vs balance
        if user_data.balance < bet:
            await interaction.response.send_message("you don't have enough como to place this bet!", ephemeral=True)
            return
        
        user_data.balance -= bet
        await user_data.save()

        # slot machine definition
        symbols = ["🍒", "🍋", "🍊", "🍇", "⭐", "💎"]
        weights = [0.3, 0.25, 0.2, 0.15, 0.07, 0.03]

        reel_1 = random.choices(symbols, weights)[0]
        reel_2 = random.choices(symbols, weights)[0]
        reel_3 = random.choices(symbols, weights)[0]

        result = [reel_1, reel_2, reel_3]
        payout = 0

        payout_multipliers = {
            "🍒": 2,  # Common symbol, lower payout
            "🍋": 3,
            "🍊": 5,
            "🍇": 10,
            "⭐": 20,
            "💎": 50  # Rare symbol, higher payout
        }

        if result.count(reel_1) == 3:
            payout = bet * payout_multipliers[reel_1]
        elif result.count(reel_1) == 2 or result.count(reel_2) == 2:
            payout = bet * 1.5
        
        user_data.balance += payout
        await user_data.save()

        # slots display
        slot_display = f"🎰 **SLOTS** 🎰\n| {reel_1} | {reel_2} | {reel_3} |\n"

        if payout / bet == 2:
            result_message = f"🎉Win! {interaction.user.mention} won **{payout} como**! 🎉"
        elif payout / bet == 3:
            result_message = f"🎉 Small win! {interaction.user.mention} won **{payout} como**! 🎉"
        elif payout / bet == 5:
            result_message = f"🎉 Big win! {interaction.user.mention} won **{payout} como**! 🎉"
        elif payout / bet == 10:
            result_message = f"🎉 Huge win! {interaction.user.mention} won **{payout} como**! 🎉"
        elif payout / bet == 20:
            result_message = f"🎉 Tremendous win! {interaction.user.mention} won **{payout} como**! 🎉"
        elif payout / bet == 50:
            result_message = f"🎉 JACKPOT!!! {interaction.user.mention} won **{payout} como**!!! 🎉"
        elif payout / bet == 1.5:
            result_message = f"🎉 {interaction.user.mention} won **{payout} como**! 🎉"
        else: 
            result_message = "😢 Better luck next time!"
        
        await interaction.response.send_message(f"{slot_display}\n\n{result_message}")
    
    @slots_command.error
    async def slots_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            remaining = int(error.retry_after)
            minutes, seconds = divmod(remaining, 60)
            time_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
            await interaction.response.send_message(
                f"Slots are on cooldown! Try again in **{time_str}**.",
                ephemeral=True
            )
        else:
            raise error

    @app_commands.command(name="refresh_shop", description="Force refresh shop if issues. Admin only.")
    @app_commands.checks.has_permissions(administrator=True)
    async def manual_refresh_shop_command(self, interaction:discord.Interaction):
        await self.refresh_shop()
        await interaction.response.send_message("Manual shop refresh complete.", ephemeral=True)

    @app_commands.command(name="transfer", description="Transfer como to another user.")
    @app_commands.describe(
        recipient="The user to transfer como to.",
        amount="The amount of como to transfer."
    )
    async def transfer_command(self, interaction: discord.Interaction, recipient: discord.User, amount: int):
        sender_id = interaction.user.id
        recipient_id = recipient.id

        # prevent self transfers
        if sender_id == recipient_id:
            await interaction.response.send_message("You can't transfer como to yourself!", ephemeral=True)
            return
        
        # prevent negative/zero transfers
        if amount <= 0:
            await interaction.response.send_message("You must send more than 0 como.", ephemeral=True)
            return
        
        # get data
        sender_data = await self.get_user_data(id=sender_id)
        recipient_data = await self.get_user_data(id=recipient_id)

        # check balance
        if sender_data.balance < amount:
            await interaction.response.send_message(f"{interaction.user.mention} doesn't have enough como to complete their send to {recipient.name}! Broke ahh")
            return
        
        # transfer!
        sender_data.balance -= amount
        recipient_data.balance += amount
        await sender_data.save()
        await recipient_data.save()

        # confirmation message
        await interaction.response.send_message(f"# Transfer complete\n{interaction.user.mention} transferred **{amount}** como to {recipient.mention}!")
async def setup(bot: Bot):
    await bot.add_cog(EconomyPlugin(bot))