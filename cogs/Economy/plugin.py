from __future__ import annotations

import os
import asyncio
import discord
import random
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
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
        if not self.refresh_shop_task.is_running():
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

        # check if chase already set
        if pity_entry.chase_objekt_slug:
            current_chase = await ObjektModel.filter(slug=pity_entry.chase_objekt_slug).first()
            current_chase_name = f"{current_chase.member} {current_chase.season[0]}{current_chase.series}" if current_chase else "Unknown"

            # confirm chase change
            class ConfirmChaseChangeView(View):
                def __init__(self):
                    super().__init__()
                    self.value = None
                
                @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
                async def confirm(self, interaction: discord.Interaction, button: Button):
                    self.value = True
                    await interaction.response.defer()
                    self.stop()
                
                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
                async def cancel(self, interaction: discord.Interaction, button: Button):
                    self.value = False
                    await interaction.response.defer()
                    self.stop()
            
            view = ConfirmChaseChangeView()
            await interaction.response.send_message(
                f"You already are chasing **{current_chase_name}**! "
                f"Changing your chase objekt will reset your pity. Do you wish to proceed?",
                view=view,
                ephemeral=True
            )
            await view.wait()

            if view.value is None or not view.value:
                await interaction.followup.send("Chase objekt change canceled.", ephemeral=True)
                return
        
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
        
        rarity_to_como = {
                1: 1,
                2: 5,
                3: 15,
                4: 35,
                5: 75,
                6: 200,
                7: 5,
        }

        como_reward = rarity_to_como.get(card.rarity, 0)
        user_data = await self.get_user_data(id=user_id)
        user_data.balance += como_reward
        await user_data.save()

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
            footer_text = (
                f"Don't forget to set a new chase objekt with /set_chase!\n"
                f"You earned {como_reward} como from this spin!"
            )
            embed.set_footer(text="{footer_text}")
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
            footer_text = (
                f"{copies_message}\n"
                f"General Pity: {general_pity} | Chase Pity: {chase_pity}/250\n"
                f"You earned **{como_reward} como** from this spin!"
            )
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

    @app_commands.command(name="inv_text", description="View your or another user's inventory in text-only format. Dynamic sort available.")
    @app_commands.describe(user="The user whose inventory will be displayed. (Leave blank to view your own)",
                           filter_by_member="Filter the inventory by member. (Leave blank for no filter)",
                           filter_by_season="Filter the inventory by season.. (Leave blank for no filter)",
                           filter_by_class="Filter the inventory by class. (Leave blank for no filter)",
                           ascending="Sort the inventory in ascending order. (Leave blank to sort in descending order)")
    @app_commands.choices(
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
    async def inv_text_command(self, interaction: discord.Interaction, user: discord.User | None = None, filter_by_member: str | None = None, filter_by_season: str | None = None, filter_by_class: str | None = None, ascending: bool | None = False):
        target = user or interaction.user
        user_id = str(target.id)
        prefix = f"Your ({target})" if not user else f"{user}'s"

        await interaction.response.defer()

        query = CollectionModel.filter(user_id=user_id).prefetch_related("objekt")

        if filter_by_member:
            query = query.filter(objekt__member=filter_by_member.lower())
        if filter_by_season:
            query = query.filter(objekt__season=filter_by_season)
        if filter_by_class:
            query = query.filter(objekt__class_=filter_by_class)
        
        objekts = await query

        if not objekts:
            await interaction.followup.send(f"{prefix} inventory is empty!")
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

        items_per_page = 9
        total_pages = (len(objekt_data) + items_per_page - 1) // items_per_page
        current_page = 0
        current_sort = "date"

        def sort_inventory(data, sort_by, ascending):
            if sort_by  == "member":
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
        
        def get_page_embed(page, sort_by, ascending):
            sorted_data = sort_inventory(objekt_data, sort_by, ascending)
            start = page* items_per_page
            end = start + items_per_page
            page_objekts = sorted_data[start:end]

            desc_lines = [
                f"**{member}** {season[0]}{series} x{copies}"
                for _, member, season, _, series, _, _, copies in page_objekts
            ]

            embed = discord.Embed(
                title=f"{prefix} Inventory (Page {page + 1}/{total_pages})",
                description='\n'.join(desc_lines),
                color=0xb19cd9
            )
            return embed
        
        class InventoryView(View):
            def __init__(self):
                super().__init__()
                self.current_page = 0
                self.current_sort = "date"
                self.ascending = ascending
            
            async def update_embed(self, interaction: discord.Interaction):
                embed = get_page_embed(self.current_page, self.current_sort, self.ascending)
                await interaction.response.edit_message(embed=embed, view=self)
            
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

            @discord.ui.button(label="Sort by Member", style=discord.ButtonStyle.blurple)
            async def sort_by_member(self, interaction: discord.Interaction, button: Button):
                self.current_sort = "member"
                await self.update_embed(interaction)

            @discord.ui.button(label="Sort by Season", style=discord.ButtonStyle.blurple)
            async def sort_by_season(self, interaction: discord.Interaction, button: Button):
                self.current_sort = "season"
                await self.update_embed(interaction)
            
            @discord.ui.button(label="Sort by Class", style=discord.ButtonStyle.blurple)
            async def sort_by_class(self, interaction: discord.Interaction, button: Button):
                self.current_sort = "class"
                await self.update_embed(interaction)
            
            @discord.ui.button(label="Sort by Series", style=discord.ButtonStyle.blurple)
            async def sort_by_series(self, interaction: discord.Interaction, button: Button):
                self.current_sort = "series"
                await self.update_embed(interaction)
            
            @discord.ui.button(label="Sort by Rarity", style=discord.ButtonStyle.blurple)
            async def sort_by_rarity(self, interaction: discord.Interaction, button: Button):
                self.current_sort = "rarity"
                await self.update_embed(interaction)
            
            @discord.ui.button(label="Sort by Copies", style=discord.ButtonStyle.blurple)
            async def sort_by_copies(self, interaction: discord.Interaction, button: Button):
                self.current_sort = "copies"
                await self.update_embed(interaction)
            
            @discord.ui.button(label="Toggle Asc/Desc", style=discord.ButtonStyle.blurple)
            async def toggle_ascending(self, interaction: discord.Interaction, button: Button):
                self.ascending = not self.ascending
                await self.update_embed(interaction)

        embed = get_page_embed(current_page, current_sort, ascending)
        view = InventoryView()
        await interaction.followup.send(embed=embed, view=view)     


    def create_collage(self, image_urls, filename='collage.png', thumb_size=(130, 200), images_per_row=3):
        def download_and_process_image(url):
            try:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                img = Image.open(BytesIO(response.content))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGBA")
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img=background
                else:
                    img=img.convert("RGB")
                img.thumbnail(thumb_size)
                return img
            except Exception as e:
                print(f"Error loading image from {url}: {e}")
                return None
        
        with ThreadPoolExecutor() as executor:
            images = list(filter(None, executor.map(download_and_process_image, image_urls)))
            
        rows = (len(images) + images_per_row - 1) // images_per_row
        collage_width = thumb_size[0] * images_per_row
        collage_height = thumb_size[1] * rows
        collage = Image.new('RGBA', (collage_width, collage_height), (255, 255, 255))

        for index, img in enumerate(images):
            x = (index % images_per_row) * thumb_size[0]
            y = (index // images_per_row) * thumb_size[1]
            collage.paste(img, (x, y))
        
        collage.save(filename, format='PNG')
        return filename

    @app_commands.command(name="inv_images", description="View your or another user's inventory.")
    @app_commands.describe(
        user="The user whose inventory will be displayed. (Leave blank for your own)",
        sort_by="The sorting criteria for the inventory.",
        filter_by_member="Filter the inventory by member. (Leave blank for no filter)",
        filter_by_season="Filter the inventory by season. (Leave blank for no filter)",
        filter_by_class="Filter the inventory by class. (Leave blank for no filter)",
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
                          sort_by: app_commands.Choice[str] | None = None,
                          filter_by_member: str | None = None,
                          filter_by_season: str | None = None,
                          filter_by_class: str | None = None,
                          ascending: bool | None = False
                          ):
        target = user or interaction.user
        user_id = str(target.id)
        prefix = f"Your ({target})" if not user else f"{user}'s"

        await interaction.response.defer()

        query = CollectionModel.filter(user_id=user_id).prefetch_related("objekt")

        if filter_by_member:
            query = query.filter(objekt__member=filter_by_member)
        if filter_by_season:
            query = query.filter(objekt__season=filter_by_season)
        if filter_by_class:
            query = query.filter(objekt__class_=filter_by_class)
        
        objekts = await query

        if not objekts:
            await interaction.followup.send(f"{prefix} inventory is empty!")
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
                objekt.updated_at,
                objekt.copies
            )
            for objekt in objekts
        ]

        sort_by_value = sort_by.value if sort_by else "updated_at"

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
                return sorted(data, key=lambda x: x[8], reverse=not ascending)
            else:
                return sorted(data, key=lambda x: x[7], reverse=not ascending)
        
        sorted_data = sort_inventory(objekt_data, sort_by_value, ascending)
        image_urls = [url for _, _, _, _, _, url, _, _, _ in sorted_data if url]

        if not image_urls:
            await interaction.followup.send(f"{prefix} inventory has no images to display!", ephemeral=True)
            return
        
        items_per_page = 9
        total_pages = (len(objekt_data) + items_per_page - 1) // items_per_page
        current_page = 0

        def create_collage_for_page(page):
            start = page * items_per_page
            end = start + items_per_page
            page_image_urls = image_urls[start:end]
            page_objekts = sorted_data[start:end]
            desc_lines = [
                f"**{member}** {season[0]}{series} x{copies}"
                for _, member, season, _, series, _, _, _, copies in page_objekts
            ]
            description = "\n".join(desc_lines)
            collage_path = self.create_collage(page_image_urls, filename=f'collage_{target.name}_page_{page}.png')
            return collage_path, description
        
        class InventoryImageView(View):
            def __init__(self):
                super().__init__()
                self.current_page = 0
                
            async def update_embed(self, interaction: discord.Interaction):
                try:
                    collage_path, description = create_collage_for_page(self.current_page)
                    file = discord.File (collage_path, filename="collage.png")

                    embed = discord.Embed(
                        title=f"{prefix} Inventory (Page {self.current_page + 1}/{total_pages})",
                        description=f"{description}",
                        color=0xb19cd9
                    )
                    embed.set_image(url="attachment://collage.png")

                    if interaction.response.is_done():
                        await interaction.followup.send(embed=embed, file=file, view=self)
                    else:
                        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
                    if os.path.exists(collage_path):
                        os.remove(collage_path)
                except  discord.errors.NotFound:
                    await interaction.followup.send("This interaction has expired. Please try again.", ephemeral=True)
                
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
        
        collage_path, description = create_collage_for_page(current_page)
        file = discord.File(collage_path, filename="collage.png")
        embed= discord.Embed(
            title=f"{prefix} Inventory (Page {current_page + 1}/{total_pages})",
            description=f"{description}",
            color=0xb19cd9
        )
        embed.set_image(url="attachment://collage.png")

        view = InventoryImageView()
        await interaction.followup.send(embed=embed, file=file, view=view)

        if os.path.exists(collage_path):
            os.remove(collage_path)
        
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
            1: 50,
            2: 150,
            3: 350,
            4: 750,
            5: 2000,
            6: 10000,
        }
        rarity_tiers = [1, 2, 3, 4, 5, 6]

        for user in users:
            user_id = user.id
            items = []
            for _ in range(6):
                rarity = random.choice(rarity_tiers)
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
        reel_1_weights = [0.5, 0.25, 0.15, 0.07, 0.025, 0.005]  # Higher chance for common symbols
        reel_2_weights = [0.45, 0.3, 0.15, 0.07, 0.025, 0.005]
        reel_3_weights = [0.4, 0.3, 0.2, 0.07, 0.025, 0.005]

        reel_1 = random.choices(symbols, reel_1_weights)[0]
        reel_2 = random.choices(symbols, reel_2_weights)[0]
        reel_3 = random.choices(symbols, reel_3_weights)[0]

        result = [reel_1, reel_2, reel_3]
        payout = 0

        payout_multipliers = {
            "🍒": 3,  # Common symbol, lower payout
            "🍋": 4,
            "🍊": 5,
            "🍇": 6,
            "⭐": 7,
            "💎": 10  # Rare symbol, higher payout
        }

        if result.count(reel_1) == 3:
            payout = bet * payout_multipliers[reel_1]
        elif result.count(reel_1) == 2 or result.count(reel_2) == 2:
            payout = bet * 2
        
        user_data.balance += payout
        await user_data.save()

        # slots display
        slot_display = f"🎰 **SLOTS** 🎰\n| {reel_1} | {reel_2} | {reel_3} |\n"

        if payout / bet == 3:
            result_message = f"🎉Win! {interaction.user.mention} won **{payout} como**! 🎉"
        elif payout / bet == 4:
            result_message = f"🎉 Small win! {interaction.user.mention} won **{payout} como**! 🎉"
        elif payout / bet == 5:
            result_message = f"🎉 Big win! {interaction.user.mention} won **{payout} como**! 🎉"
        elif payout / bet == 6:
            result_message = f"🎉 Huge win! {interaction.user.mention} won **{payout} como**! 🎉"
        elif payout / bet == 7:
            result_message = f"🎉 Tremendous win! {interaction.user.mention} won **{payout} como**! 🎉"
        elif payout / bet == 10:
            result_message = f"🎉 JACKPOT!!! {interaction.user.mention} won **{payout} como**!!! 🎉"
        elif payout / bet == 2:
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

    @app_commands.command(name="compare", description="Compare two users' inventories.")
    @app_commands.describe(
        user1="The first user to compare. (deafulats to command caller)",
        user2="The second user to compare."
    )
    async def compare_inventories_command(self, interaction: discord.Interaction, user2: discord.User, user1: discord.User | None = None):
        if user1:
            user1_id = str(user1.id)
            user2_id = str(user2.id)
        else:
            user1 = interaction.user
            user1_id = str(user1.id)
            user2_id = str(user2.id)
        
        # fetch inventory
        user1_inventory = await CollectionModel.filter(user_id=user1_id).prefetch_related("objekt")
        user2_inventory = await CollectionModel.filter(user_id=user2_id).prefetch_related("objekt")

        # extract slugs to compare
        user1_objekts = {entry.objekt.slug for entry in user1_inventory}
        user2_objekts = {entry.objekt.slug for entry in user2_inventory}

        # differentials
        user1_only = user1_objekts - user2_objekts
        user2_only = user2_objekts - user1_objekts

        # fetch objekt details
        user1_only_details = await ObjektModel.filter(slug__in=user1_only).all()
        user2_only_details = await ObjektModel.filter(slug__in=user2_only).all()

        user1_field_data = [
            f"[{obj.member} {obj.season[0]}{obj.series}]({obj.image_url})" for obj in user1_only_details
        ]
        user2_field_data = [
            f"[{obj.member} {obj.season[0]}{obj.series}]({obj.image_url})" for obj in user2_only_details
        ]

        # preparing pagination
        items_per_page = 9
        total_pages = max(
            (len(user1_field_data) + items_per_page - 1) // items_per_page,
            (len(user2_field_data) + items_per_page - 1) // items_per_page,
        )
        current_page = 0

        def get_page_embed(page):
            start = page * items_per_page
            end = start + items_per_page

            user1_page_data = user1_field_data[start:end]
            user2_page_data = user2_field_data[start:end]

            user1_field = "\n".join(user1_page_data)[:1024] or "None"
            user2_field = "\n".join(user2_page_data)[:1024] or "None"

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
                
            
            @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.gray)
            async def next_page(self, interaction: discord.Interaction, button: Button):
                if self.current_page < total_pages - 1:
                    self.current_page += 1
                elif self.current_page == total_pages - 1:
                    self.current_page = 0
                await self.update_embed(interaction)
        
        # send the initial embed within the View
        embed = get_page_embed(current_page)
        view = PaginationView()
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="collection_percentage", description="View your collection completion percentage.")
    @app_commands.describe(user="Indicate who's collection to view. (Leave blank to view your own)",
                           member="View your collection for a specific member.",
                           season="View your collection for a specifc season.",
                           class_="View your collection for a specific class of objekts")
    @app_commands.choices(
        season=[
            app_commands.Choice(name="atom", value="Atom01"),
            app_commands.Choice(name="binary", value="Binary01"),
            app_commands.Choice(name="cream", value="Cream01"),
            app_commands.Choice(name="divine", value="Divine01"),
            app_commands.Choice(name="ever", value="Ever01"),
            app_commands.Choice(name="customs", value="GNDSG00")
        ],
        class_=[
            app_commands.Choice(name="customs", value="Never"),
            app_commands.Choice(name="first", value="First"),
            app_commands.Choice(name="double", value="Double"),
            app_commands.Choice(name="special", value="Special"),
            app_commands.Choice(name="welcome", value="Welcome"),
            app_commands.Choice(name="zero", value="Zero"),
            app_commands.Choice(name="premier", value="Premier")
        ]
    )
    async def collection_percentage_command(self, interaction: discord.Interaction, user: discord.User | None = None, member: str | None = None, season: app_commands.choice[str] | None = None, class_: app_commands.Choice[str] | None = None):
        target = user or interaction.user
        user_id = str(target.id)
        prefix = f"Your ({target})" if not user else f"{user}'s"

        # only one filter at a time
        active_filters = sum(bool(x) for x in [member, season, class_])
        if active_filters > 1:
            await interaction.response.send_message("You can only filter by one of `member`, `Season`, or `class` at a time.", ephemeral=True)
            return

        # apply filters
        query = ObjektModel.all()
        if member:
            query = query.filter(member__iexact=member)
        if season:
            query = query.filter(season=season.value)
        if class_:
            query = query.filter(class_=class_.value)
        
        # fetch objekts based on filters
        total_objekts = await query.all()

        # feth user's filtered collected objekts
        collected_objekts = await CollectionModel.filter(user_id=user_id, objekt__in=total_objekts).prefetch_related("objekt")
        collected_ids = {entry.objekt.id for entry in collected_objekts}

        # separate collected from missing
        collected = [objekt for objekt in total_objekts if objekt.id in collected_ids]
        missing = [objekt for objekt in total_objekts if objekt.id not in collected_ids]

        total_count = len(total_objekts)
        collected_count = len(collected)
        if total_objekts == 0:
            collection_percentage = 0
        else:
            collection_percentage = (collected_objekts / total_objekts) * 100
        
        if member:
            title = f"{prefix} Collection ({member}):"
        elif season:
            title = f"{prefix} Collection ({season.name}):"
        elif class_:
            title = f"{prefix} Collection ({class_.name}):"
        else:
            title = f"{prefix} Collection:"

        items_per_page = 9
        total_pages = max((len(collected) + items_per_page - 1) // items_per_page, (len(missing) + items_per_page - 1) // items_per_page)
        current_page = 0

        def get_page_embed(page):
            start = page * items_per_page
            end = start + items_per_page

            collected_page = collected[start:end]
            missing_page = missing[start:end]

            collected_details = [
                f"{objekt.member} {objekt.season[0]}{objekt.series}" for objekt in collected_page
            ]
            missing_details = [
                f"{objekt.member} {objekt.season[0]}{objekt.series}" for objekt in missing_page
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
            
        embed = get_page_embed(current_page)
        view = PaginationView()
        await interaction.response.send_message(embed=embed, view=view)


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
        
        await interaction.response.send_message(embed=embed)


async def setup(bot: Bot): 
    await bot.add_cog(EconomyPlugin(bot))