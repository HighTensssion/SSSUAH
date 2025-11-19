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

__all__ = ("update_user_balance", "add_objekt_to_user")

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
    
    async def get_cooldown(self, user_id: int, command: str):
        return await CooldownModel.filter(user_id=user_id, command=command).first()

    async def set_cooldown(self, user_id: int, command: str, expires_at: datetime):
        cooldown = await self.get_cooldown(user_id, command)
        if cooldown:
            cooldown.expires_at = expires_at
            await cooldown.save()
        else:
            await CooldownModel.create(user_id=user_id, command=command, expires_at=expires_at)

    async def update_user_balance(self, user_id: int, amount: int):
        user_data = await self.get_user_data(id=user_id)
        user_data.balance += amount
        await user_data.save()

    async def get_random_objekt_by_rarity(self, rarity: int):
        objekt_ids = await ObjektModel.filter(rarity=rarity).values_list("id", flat=True)
        if not objekt_ids:
            return None
        random_objekt_id = random.choice(objekt_ids)
        return await ObjektModel.get(id=random_objekt_id)

    async def add_objekt_to_user(self, user_id: int, objekt: ObjektModel):
        async with in_transaction():
            collection_entry = await CollectionModel.filter(user_id=str(user_id), objekt_id=objekt.id).first()
            if collection_entry:
                collection_entry.copies += 1
                await collection_entry.save()
            else:
                await CollectionModel.create(user_id=str(user_id), objekt_id=objekt.id, copies=1)

    async def get_ready_commands(self, user_id: int, now: datetime, commands: list[str]):
        reminders = []
        for command in commands:
            cooldown = await self.get_cooldown(user_id, command)
            if not cooldown or cooldown.expires_at <= now:
                reminders.append(command.capitalize())
        return reminders

    def create_daily_reward_embed(self, como_amount: int, objekt: ObjektModel, reminders: list[str]):
        color = int(objekt.background_color.replace("#", ""), 16) if objekt.background_color else 0xFF69B4
        embed = discord.Embed(
            title="Daily Reward!",
            description=f"You received **{como_amount:,} como** and **{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}**!",
            color=color
        )
        if objekt.class_ == "motion" and objekt.front_media:
            embed.add_field(name="Preview", value=f"[Click here to view the motion video]({card.frontMedia})", inline=False)
        elif objekt.image_url:
            embed.set_image(url=objekt.image_url)
        if reminders:
            embed.set_footer(text=f"Reminder: {', '.join(reminders)} command(s) are ready!")
        return embed

    def format_time_difference(self, time_delta: timedelta):
        minutes, seconds = divmod(time_delta.total_seconds(), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{int(hours)}h {int(minutes)}m"

    def create_weekly_reward_embed(self, como_amount: int, objekt: ObjektModel, reminders: list[str]):
        color = int(objekt.background_color.replace("#", ""), 16) if objekt.background_color else 0xFF69B4
        embed = discord.Embed(
            title="Weekly Reward!",
            description=f"You received **{como_amount:,} como** and **{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}**!",
            color=color
        )
        if objekt.class_ == "motion" and objekt.front_media:
            embed.add_field(name="Preview", value=f"[Click here to view the motion video]({card.frontMedia})", inline=False)
        elif objekt.image_url:
            embed.set_image(url=objekt.image_url)
        if reminders:
            embed.set_footer(text=f"Reminder: {', '.join(reminders)} command(s) are ready!")
        return embed

    async def get_objekt_ids_for_banner(self, rarity_choice: int, banner: str | None):
        if banner == "rateup":
            return await self.handle_rateup_banner(rarity_choice)
        elif banner:
            return await self.handle_specific_banner(rarity_choice, banner)
        else:
            return await ObjektModel.filter(rarity=rarity_choice).values_list("id", flat=True)

    async def handle_rateup_banner(self, rarity_choice: int):
        if rarity_choice == 1:
            sub_rarity = ["Binary02", "GNDSG01"]
            sub_weights = [0.3, 0.7]
            season_choice = await self.rarity_choice(sub_rarity, sub_weights)
            return await ObjektModel.filter(season=season_choice, rarity=rarity_choice).values_list("id", flat=True)
        else:
            return await ObjektModel.filter(Q(season="Binary02"), rarity=rarity_choice).values_list("id", flat=True)

    async def handle_specific_banner(self, rarity_choice: int, banner: str):
        if rarity_choice == 1:
            sub_rarity = [banner, "GNDSG01"]
            sub_weights = [0.3, 0.7]
            season_choice = await self.rarity_choice(sub_rarity, sub_weights)
            return await ObjektModel.filter(season=season_choice, rarity=rarity_choice).values_list("id", flat=True)
        else:
            return await ObjektModel.filter(season=banner, rarity=rarity_choice).values_list("id", flat=True)

    async def handle_pity(self, user_id: int, ids: list[int], pity_entry: PityModel, banner: str | None, rarity_choice: int):
        if pity_entry.chase_objekt_slug:
            card, pity_taken = await self.handle_chase_pity(user_id, ids, pity_entry)
            if card:
                return card, pity_taken

        return await self.handle_general_pity(user_id, ids, pity_entry, banner, rarity_choice)

    async def handle_chase_pity(self, user_id: int, ids: list[int], pity_entry: PityModel):
        chase_objekt = await ObjektModel.filter(slug=pity_entry.chase_objekt_slug).first()
        if chase_objekt and chase_objekt.id in ids:
            random_id = random.choice(ids)
            card = await ObjektModel.get(id=random_id)

            if card.id == chase_objekt.id:
                return await self.reset_chase_pity(user_id, card, pity_entry)

        pity_entry.chase_pity_count += 1
        if pity_entry.chase_pity_count >= 250:
            return await self.reset_chase_pity(user_id, chase_objekt, pity_entry)

        await pity_entry.save()
        return None, None

    async def reset_chase_pity(self, user_id: int, card: ObjektModel, pity_entry: PityModel):
        pity_taken = pity_entry.chase_pity_count
        pity_entry.chase_pity_count = 0
        pity_entry.chase_objekt_slug = None
        pity_entry.pity_count = 0
        await pity_entry.save()

        await self.add_objekt_to_user(user_id, card)
        return card, pity_taken

    async def handle_general_pity(self, user_id: int, ids: list[int], pity_entry: PityModel, banner: str | None, rarity_choice: int):
        low_rarities = [1, 2, 3, 4]
        if rarity_choice in low_rarities:
            pity_entry.pity_count += 1
        else:
            pity_entry.pity_count = 0

        if pity_entry.pity_count >= 80:
            return await self.reset_general_pity(user_id, pity_entry, banner)

        await pity_entry.save()
        return None, None

    async def reset_general_pity(self, user_id: int, pity_entry: PityModel, banner: str | None):
        pity_entry.pity_count = 0
        owned_ids = await CollectionModel.filter(user_id=user_id).values_list("objekt_id", flat=True)

        if banner:
            higher_rarity_cards = await ObjektModel.filter(rarity__gte=4, season=banner).exclude(id__in=owned_ids).values_list("id", flat=True)
        else:
            higher_rarity_cards = await ObjektModel.filter(rarity__gte=4).exclude(id__in=owned_ids).values_list("id", flat=True)

        if higher_rarity_cards:
            pity_card_id = random.choice(higher_rarity_cards)
            pity_card = await ObjektModel.get(id=pity_card_id)
            await self.add_objekt_to_user(user_id, pity_card)
            await pity_entry.save()
            return pity_card, None

        await pity_entry.save()
        return None, None

    async def select_random_objekt(self, user_id: int, ids: list[int]):
        random_id = random.choice(ids)
        card = await ObjektModel.get(id=random_id)

        if not card:
            return None, None

        await self.add_objekt_to_user(user_id, card)
        return card, None

    async def rarity_choice(self, rarity, weights):
        if not rarity:
            return None
        return random.choices(rarity, weights=weights)[0]

    async def give_random_objekt(self, user_id: int, banner: str | None = None, pity_entry: PityModel | None = None):
        rarity = [6,5,4,3,2,1]
        weights = [0.003,0.03,0.067,0.1,0.2,0.6]
        rarity_choice = await self.rarity_choice(rarity, weights)
        
        # handle banners
        ids = await self.get_objekt_ids_for_banner(rarity_choice, banner)

        if not ids:
            return None, None
        
        if pity_entry:
            card, pity_taken = await self.handle_pity(user_id, ids, pity_entry, banner, rarity_choice)
            if card:
                return card, pity_taken
        
        return await self.select_random_objekt(user_id, ids)

    async def validate_objekt_slug(self, objekt_slug: str) -> ObjektModel | None:
        return await ObjektModel.filter(slug=objekt_slug).first()

    async def confirm_chase_change(self, interaction: discord.Interaction, pity_entry: PityModel) -> bool:
        current_chase = await ObjektModel.filter(slug=pity_entry.chase_objekt_slug).first()
        current_chase_name = (
            f"{current_chase.member} {current_chase.season[0] * int(current_chase.season[-1])}{current_chase.series}"
            if current_chase else "Unknown"
        )

        class ConfirmChaseChangeView(View):
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

        view = ConfirmChaseChangeView(user_id=interaction.user.id)
        await interaction.followup.send(
            f"You are already chasing **{current_chase_name}**! Changing your chase objekt will reset your pity. Do you wish to proceed?",
            ephemeral=True,
            view=view
        )
        await view.wait()

        if view.value is None or not view.value:
            await interaction.followup.send("Chase objekt change canceled.", ephemeral=True)
            return False

        return True

    async def update_chase_objekt(self, pity_entry: PityModel, objekt_slug: str):
        pity_entry.chase_objekt_slug = objekt_slug
        pity_entry.chase_pity_count = 0
        await pity_entry.save()

    def calculate_como_reward(self, rarity: int) -> int:
        return RARITY_COMO_REWARDS.get(rarity, 0)

    async def create_spin_embed(
        self,
        user: discord.User,
        card: ObjektModel,
        pity_entry: PityModel,
        pity_taken: int | None,
        como_reward: int,
        reminders: list[str]
    ) -> discord.Embed:
        color = int(card.background_color.replace("#", ""), 16) if card.background_color else 0xFF69B4
        
        rarity_str = RARITY_STR_MAPPING.get(card.rarity, "n ")
        
        collection_entry = await CollectionModel.filter(user_id=str(user.id), objekt_id=card.id).first()        
        if collection_entry and collection_entry.copies > 1:
            copies_message = f"You now have {collection_entry.copies} copies of this objekt!"
        else:
            copies_message = "Congrats on your new objekt!"

        # Check if chase target is reached
        if pity_taken:
            title = f"Congratulations, {user}, after {pity_taken} spins, your chase ended!"
            footer_text = (
                f"Don't forget to set a new chase objekt with /set_chase!\n"
                f"You earned {como_reward} como from this spin!"
            )
        else:
            title = f"You ({user}) received a{rarity_str}objekt!"
            general_pity = pity_entry.pity_count if pity_entry else 0
            chase_pity = pity_entry.chase_pity_count if pity_entry else 0
            footer_text = (
                f"{copies_message}\n"
                f"General Pity: {general_pity} | Chase Pity: {chase_pity}/250\n"
                f"You earned {como_reward} como from this spin!"
            )

        if reminders:
            footer_text += f"\nReminder: {', '.join(reminders)} command(s) are ready!"

        embed = discord.Embed(title=title, color=color)
        embed.description = f"[{card.member} {card.season[0] * int(card.season[-1])}{card.series}]({card.image_url})"
        
        if card.class_ == "motion" and card.front_media:
            embed.add_field(name="Preview", value=f"[Click here to view the motion video]({card.frontMedia})", inline=False)
        elif card.image_url:
            embed.set_image(url=card.image_url)
        
        embed.set_footer(text=footer_text)

        return embed

    def create_sell_callback(self, user_id: str, rarity: int, leave: int):
        async def callback(interaction: discord.Interaction):
            if str(interaction.user.id) != user_id:
                await interaction.response.send_message("You cannot use this button. It is locked to the command caller.", ephemeral=True)
                return
            
            collection_entries = await CollectionModel.filter(user_id=user_id, objekt__rarity=rarity).prefetch_related("objekt")
            if not collection_entries:
                await interaction.response.send_message(f"You have no extra objekts of rarity {rarity} to sell!", ephemeral=True)
                return
            
            total_sold = 0
            total_value = 0
            reward_per = RARITY_COMO_REWARDS.get(rarity, 0)

            async with in_transaction():
                for entry in collection_entries:
                    if entry.copies > leave:
                        sell_count = entry.copies - leave
                        sale_value = (reward_per * 2) * sell_count
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
            
            if total_sold == 0:
                await interaction.response.send_message(f"You have no duplicates of rarity {rarity} above the leave limit to sell.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{interaction.user.name} sold **{total_sold} objekts** of rarity {rarity} for **{total_value}** como.", ephemeral=True)
            
        return callback

    async def get_rarity_summary(self, user_id: str, leave: int):
        collection_entries = await CollectionModel.filter(user_id=user_id).prefetch_related("objekt")
        rarity_summary = {}
        for entry in collection_entries:
            rarity = entry.objekt.rarity
            if rarity not in rarity_summary:
                rarity_summary[rarity] = {"unique": 0, "dupes": 0}
            rarity_summary[rarity]["unique"] += 1
            if entry.copies > leave:
                rarity_summary[rarity]["dupes"] += entry.copies - leave
        return rarity_summary
      
    async def refresh_shop(self):
        now = datetime.now(tz=timezone.utc)
        midnight = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)

        users = await EconomyModel.all()

        for user in users:
            user_id = user.id
            await ShopModel.filter(user_id=user_id).delete()

            items = []
            for _ in range(6):
                rarity = random.choice(RARITY_TIERS)
                objekt = await self.get_random_objekt_by_rarity(rarity)
                if objekt:
                    price = SHOP_BUY_VALUES.get(objekt.rarity, 0)
                    items.append(ShopModel(user_id=user_id, objekt=objekt, price=price))
            if items:
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
            
            await interaction.response.defer()
            
            user_data.balance -= shop_item.price
            await user_data.save()
            await self.add_objekt_to_user(user.id, shop_item.objekt)
            
            await interaction.followup.send(
                f"{user.mention} successfully purchased **[{shop_item.objekt.member} {shop_item.objekt.season[0] * int(shop_item.objekt.season[-1])}{shop_item.objekt.series}]({shop_item.objekt.image_url})** for **{shop_item.price}** como!", ephemeral=True
            )
        
        return callback
    
    async def get_objekt_count(self, user_id, objekt):
        entry = await CollectionModel.get_or_none(user_id=user_id, objekt=objekt)
        return entry.copies if entry else 1

    @app_commands.command(name="balance", description="Show your balance or another user's balance.")
    async def balance_command(self, interaction: discord.Interaction, user: discord.User | None):
        await interaction.response.defer()

        target = user or interaction.user
        user_data = await self.get_user_data(id=target.id)
        
        embed = discord.Embed(
            title="Balance Check",
            description=f"**{target.mention}** has **{user_data.balance:,.0f} como.**",
            color=0x00FF00
        )
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="daily", description="Claim a random amount of como daily.")
    async def daily_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        now = datetime.now(tz=timezone.utc)

        cooldown = await self.get_cooldown(user_id, "daily")
        if cooldown and cooldown.expires_at > now:
            remaining_time = self.format_time_difference(cooldown.expires_at - now)
            await interaction.followup.send(
                f"You are on cooldown! Try again in {remaining_time}.",
                ephemeral=True
            )
            return
        
        como_amount = random.randint(500, 2500)
        await self.update_user_balance(user_id, como_amount)

        rarity = random.choice([1,2])
        objekt = await self.get_random_objekt_by_rarity(rarity)
        if not objekt:
            await interaction.followup.send(
                f"You received **{como_amount:,}** como but no objekts of rarity {rarity} are available in the database.",
                ephemeral=True
            )
            return
        
        await self.add_objekt_to_user(user_id, objekt)

        await self.set_cooldown(user_id, "daily", now + timedelta(days=1))

        reminders = await self.get_ready_commands(user_id, now, ["rob", "weekly"])

        embed = self.create_daily_reward_embed(como_amount, objekt, reminders) 
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="weekly", description="Claim 5000 como and a rare objekt weekly.")
    async def weekly_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        now = datetime.now(tz=timezone.utc)
        
        cooldown = await self.get_cooldown(user_id, "weekly")
        if cooldown and cooldown.expires_at > now:
            remaining_time = self.format_time_difference(cooldown.expires_at - now)
            await interaction.followup.send(
                f"You are on cooldown! Try again in {remaining_time}.",
                ephemeral=True
            )
            return

        como_amount = 5000
        await self.update_user_balance(user_id, como_amount)

        # give objekt
        rarity_choices = [4, 5, 6]
        rarity_weights = [0.6, 0.3, 0.1]
        chosen_rarity = random.choices(rarity_choices, weights=rarity_weights, k=1)[0]
        objekt = await self.get_random_objekt_by_rarity(chosen_rarity)

        if not objekt:
            await interaction.followup.send(
                f"You received **{como_amount:,} como**, but no objekts of rarity {chosen_rarity} are available in the database.",
                ephemeral=True
            )
            return
        
        await self.add_objekt_to_user(user_id, objekt)
        
        await self.set_cooldown(user_id, "weekly", now + timedelta(days=7))

        reminders = await self.get_ready_commands(user_id, now, ["daily", "rob"])
        
        embed = self.create_weekly_reward_embed(como_amount, objekt, reminders)
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="set_chase", description="Set a chase objekt, which you will be guaranteed to receive within 250 spins.")
    @app_commands.describe(
        season="The season which your chase objekt is in.",
        member="The member whose objekt you wish to chase. (Ex. Nien, Honeydan)",
        series="The series of your desired chase objekt. (Ex. 000, 309, 901)"
    )
    @app_commands.choices(season=SEASON_CHOICES)
    async def set_chase_command(self, interaction: discord.Interaction, season: str, member: str, series: str):
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        objekt_slug = f"{season}-{member}-{series}".lower()

        # validate slug
        objekt = await self.validate_objekt_slug(objekt_slug)
        if not objekt:
            await interaction.followup.send("The specified objekt slug does not exist!", ephemeral=True)
            return
        
        # get or create the user's pity entry
        pity_entry, _ = await PityModel.get_or_create(user_id=user_id)

        # check if chase already set
        if pity_entry.chase_objekt_slug:
            if not await self.confirm_chase_change(interaction, pity_entry):
                return
        
        # update chase objekt
        await self.update_chase_objekt(pity_entry, objekt_slug)

        embed = discord.Embed(
            title="Chase Objekt Set!",
            description=f"Your chase objekt has been set to **{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}**!",
            color=int(objekt.background_color.replace("#", ""), 16) if objekt.background_color else 0x0f0
        )
        if objekt.class_ == "motion" and objekt.front_media:
            embed.add_field(name="Preview", value=f"[Click here to view the motion video]({card.frontMedia})", inline=False)
        elif objekt.image_url:
            embed.set_image(url=objekt.image_url)

        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="spin", description="Collect a random objekt!")
    @app_commands.describe(banner="Select a banner to spin from (leave blank to spin all seasons).")
    @app_commands.choices(banner=BANNER_CHOICES)
    @app_commands.checks.cooldown(1,10, key=lambda i: (i.user.id,))
    async def spin_command(self, interaction: discord.Interaction, banner: app_commands.Choice[str] | None = None):
        await interaction.response.defer()

        try:
            user_id = interaction.user.id
            banner_value = banner.value if isinstance(banner, app_commands.Choice) else banner

            reminders = await self.get_ready_commands(user_id, datetime.now(tz=timezone.utc), ["daily", "rob", "weekly"])

            # user's pity counter
            pity_entry, _ = await PityModel.get_or_create(user_id=user_id)

            # roll
            card, pity_taken = await self.give_random_objekt(user_id, banner=banner_value, pity_entry=pity_entry)

            if not card:
                await interaction.followup.send("No objekts found in the database.")
                return
            
            como_reward = self.calculate_como_reward(card.rarity)
            await self.update_user_balance(user_id, como_reward)

            embed = await self.create_spin_embed(interaction.user, card, pity_entry, pity_taken, como_reward, reminders)
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            log.error(f"An error occurred in spin_command: {e}")
            await interaction.followup.send("An error occurred while processing your spin. Please try again later.", ephemeral=True)

    @spin_command.error
    async def spin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            remaining = int(error.retry_after)
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            time_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
            await interaction.response.send_message(
                f"Try again in **{time_str}**.",
                ephemeral=True
            )
        elif isinstance(error, discord.NotFound):
            log.error("Interaction expired before the bot could respond.")
        else:
            raise error

    @app_commands.command(name="rob", description="Steal an objekt from another user.")
    @app_commands.describe(target="The user to rob.")
    async def rob_command(self, interaction: discord.Interaction, target: discord.User):
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        target_id = str(target.id)

        if target_id == user_id:
            await interaction.followup.send("You can't rob yourself! masochist.")
            return
        
        now = datetime.now(tz=timezone.utc)
        cooldown = await self.get_cooldown(user_id, "rob")

        if cooldown and cooldown.expires_at > now:
            remaining_time = self.format_time_difference(cooldown.expires_at - now)
            await interaction.followup.send(
                f"You are on cooldown! Try again in {remaining_time}.",
                ephemeral=True
            )
            return
        
        reminders = await self.get_ready_commands(user_id, now, ["daily", "weekly"])
        
        if random.random() < 0.15:
            user_data = await self.get_user_data(id=interaction.user.id)
            loss_amount = random.randint(100, 200)
            user_data.balance = max(0, user_data.balance - loss_amount)
            await user_data.save()
            await interaction.followup.send(
                f"{interaction.user.mention} attempted to rob {target.mention} but failed, losing **{loss_amount}** como in the process.\n{interaction.user} now has {user_data.balance} como left."
            )
            return

        target_inventory = await CollectionModel.filter(user_id=target_id).prefetch_related("objekt")
        if not target_inventory:
            await interaction.followup.send(f"{target} has nothing to rob!")
            return
        
        stolen_objekt = random.choice(target_inventory)
        target_data = await self.get_user_data(id=target.id)
        user_data = await self.get_user_data(id=interaction.user.id)
        stolen_como = random.randint(50, 200)
        if target_data.balance < stolen_como:
            stolen_como = target_data.balance
        
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

            target_data.balance -= stolen_como
            user_data.balance +=  stolen_como
            await target_data.save()
            await user_data.save()
        
        expires_at = now + timedelta(hours=6)
        await self.set_cooldown(user_id, "rob", expires_at)

        response = (
            f"{target.mention}, you have been robbed!\n"
            f"{interaction.user.mention} stole **{stolen_como} como** and "
            f"[{stolen_objekt.objekt.member} {stolen_objekt.objekt.season[0] * int(stolen_objekt.objekt.season[-1])}{stolen_objekt.objekt.series}]({stolen_objekt.objekt.image_url}) from you!"
        )
        if reminders:
            response += f"\nReminder: {', '.join(reminders)} command(s) are ready!"
        
        await interaction.followup.send(content=response)

    @app_commands.command(name="send", description="Send an objekt to another user.")
    @app_commands.describe(
        recipient="The user to send the objekt to.",
        season="The season that the objekt you wish to send belongs to.",
        member="The member whose objekt you wish to send. (Ex. Yooyeon, Nyangkidan)",
        series="The series of the objekt you wish to send. (Ex. 000, 100, 309)"
    )
    @app_commands.choices(season=SEASON_CHOICES)
    async def send_objekt_command(self, interaction:discord.Interaction, recipient: discord.User, season: str, member: str, series: int):
        await interaction.response.defer()

        sender_id = str(interaction.user.id)
        recipient_id = str(recipient.id)

        if sender_id == recipient_id:
            await interaction.followup.send("You can't send an objekt to yourself!", ephemeral=True)
            return
        
        objekt = await ObjektModel.filter(season__iexact=season, member__iexact=member, series=str(series)).first()
        if not objekt:
            await interaction.followup.send("Objekt not found!", ephemeral=True)
            return

        async with in_transaction():
            sender_entry = await CollectionModel.filter(user_id=sender_id, objekt_id=objekt.id).first()
            if not sender_entry or sender_entry.copies < 1:
                await interaction.followup.send("You don't have that objekt!", ephemeral=True)
                return
            
            sender_entry.copies -= 1
            if sender_entry.copies == 0:
                await sender_entry.delete()
            else:
                await sender_entry.save()

            await self.add_objekt_to_user(recipient_id, objekt)
            
        color = int(objekt.background_color.replace("#", ""), 16) if objekt.background_color else 0xff69b4
        embed = discord.Embed(
            title=f"{interaction.user.name} sends an objekt to {recipient.name}!",
            description=f"[{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}]({objekt.image_url})",
            color=color
        )
        if objekt.class_ == "motion" and objekt.front_media:
            embed.add_field(name="Preview", value=f"[Click here to view the motion video]({card.frontMedia})", inline=False)
        elif objekt.image_url:
            embed.set_image(url=objekt.image_url)

        confirmation_message = (
            f"{interaction.user.mention} sent **[{objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}]({objekt.image_url})** to {recipient.mention}!"
        )

        await interaction.followup.send(content=confirmation_message, embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
    
    @app_commands.command(name="sell", description="Sell your duplicate objekts for como. (Do not sell rarity 7 dupes, as they may go up in value)")
    @app_commands.describe(
        leave="The number of duplicates to leave in your inventory (only for bulk selling)."
    )
    async def sell_objekt_command(self, interaction: discord.Interaction, leave: int = 1):
        await interaction.response.defer()
        user_id = str(interaction.user.id)

        rarity_summary = await self.get_rarity_summary(user_id, leave)
        
        embed = discord.Embed(
            title=f"{interaction.user.name}'s Inventory Overview",
            description="Here is an overview of your inventory by rarity tier:",
            color=0xFFFFFF
        )
        for rarity in sorted(rarity_summary.keys()):
            counts = rarity_summary[rarity]
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
        
        if not any(rarity_summary[r]["dupes"] > 0 for r in rarity_summary):
            embed.set_footer(text="You have no duplicates above the leave limit to sell.")
        
        await interaction.followup.send(embed=embed, view=view if view.children else None)

    @app_commands.command(name="shop", description="View the shop.")
    async def shop_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_id = interaction.user.id
        shop_items = await ShopModel.filter(user_id=user_id).prefetch_related("objekt")

        if not shop_items:
            await interaction.followup.send("Your shop is currently empty. Please wait for the next refresh!")
            return
        
        now = datetime.now(tz=timezone.utc)
        next_refresh = datetime.combine(now.date(), time.min, tzinfo=timezone.utc) + timedelta(days=1)
        time_remaining = next_refresh - now
        refresh_timer = self.format_time_difference(time_remaining)
        
        embed = discord.Embed(
            title=f"{interaction.user.name}'s Shop",
            description=f"Shop refreshes in: **{refresh_timer}**",
            color=0x000000
        )

        view = View()
        for idx, item in enumerate(shop_items, start=1):
            objekt = item.objekt
            collection_entry = await CollectionModel.filter(user_id=str(user_id), objekt_id=objekt.id).first()
            owned = f"Owned: **{collection_entry.copies}**" if collection_entry else "Not Owned"
            embed.add_field(
                name=f"{idx}. {objekt.member} {objekt.season[0] * int(objekt.season[-1])}{objekt.series}",
                value=(
                    f"Rarity: {objekt.rarity}\n"
                    f"Price: {item.price:,} como\n"
                    f"{owned}\n"
                    f"[View Objekt]({objekt.image_url})"
                ),
                inline=True
            )
            button = Button(label=f"Buy #{idx}", style=discord.ButtonStyle.blurple)
            button.callback = self.create_purchase_callback(item, interaction.user)
            button.row = (idx - 1) // 3
            view.add_item(button)

        await interaction.followup.send(embed=embed, view=view)
    
    @app_commands.command(name="slots", description="Bet your como and spin the slot machine!")
    @app_commands.describe(
        bet="The amount of como to bet on the slot machine, or 'all' to go all in."
    )
    @app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id,))
    async def slots_command(self, interaction: discord.Interaction, bet: str):
        await interaction.response.defer()

        user_id = interaction.user.id
        user_data = await self.get_user_data(id=user_id)

        if isinstance(bet, str) and bet.lower() in ("all", "max", "all in"):
            bet_amount = user_data.balance
        elif isinstance(bet, str) and bet.lower() in ("half"):
            bet_amount = (user_data.balance // 2)
        else:
            try:
                bet_amount = int(bet)
            except (ValueError, TypeError):
                await interaction.followup.send("Invalid bet amount! Please enter a valid number or 'all'.", ephemeral=True)
                return

        # check valid bet
        if bet_amount <= 0:
            await interaction.followup.send("Your bet must be greater than 0!", ephemeral=True)
            return
        if user_data.balance < bet_amount:
            await interaction.followup.send("You don't have enough como to place this bet! Broke ahh")
            return
        
        user_data.balance -= bet_amount
        await user_data.save()

        # slot machine definition
        symbols = ["🍒", "🍋", "🍊", "🍇", "⭐", "💎"]
        reel_weights = [
            [0.6, 0.2, 0.1, 0.05, 0.04, 0.01],
            [0.1, 0.5, 0.2, 0.1, 0.08, 0.02],
            [0.05, 0.1, 0.5, 0.15, 0.08, 0.02],
        ]
        payout_multipliers = {
            "🍒": 3,  
            "🍋": 4,
            "🍊": 5,
            "🍇": 6,
            "⭐": 7,
            "💎": 10  
        }

        reels = [random.choices(symbols, w)[0] for w in reel_weights]
        result = reels
        payout = 0

        if result.count(result[0]) == 3:
            payout = bet_amount * payout_multipliers[result[0]]
        elif result.count(result[0]) == 2 or result.count(result[1]) == 2:
            payout = bet_amount * 2
        
        user_data.balance += payout
        await user_data.save()

        payout_ratio = payout // bet_amount if bet_amount > 0 else 0

        # slots display
        slot_display = f"| {result[0]} | {result[1]} | {result[2]} |"

        embed = discord.Embed(
            title="🎰 SLOTS 🎰",
            description=slot_display,
            color=0xffd700 if payout > 0 else 0x888888
        )

        if payout_ratio == 3:
            result_message = f"🎉Win! {interaction.user} bet {bet_amount:,} como and wins **{payout:,} como**! 🎉\n {interaction.user} now has {user_data.balance:,} como."
        elif payout_ratio == 4:
            result_message = f"🎉 Small win! {interaction.user} bet {bet_amount:,} como and wins **{payout:,} como**! 🎉\n {interaction.user} now has {user_data.balance:,} como."
        elif payout_ratio == 5:
            result_message = f"🎉 Big win! {interaction.user} bet {bet_amount:,} como and wins **{payout:,} como**! 🎉\n {interaction.user} now has {user_data.balance:,} como."
        elif payout_ratio == 6:
            result_message = f"🎉 Huge win! {interaction.user} bet {bet_amount:,} como and wins **{payout:,} como**! 🎉\n {interaction.user} now has {user_data.balance:,} como."
        elif payout_ratio == 7:
            result_message = f"🎉 Tremendous win! {interaction.user} bet {bet_amount:,} como and wins **{payout:,} como**! 🎉\n {interaction.user} now has {user_data.balance:,} como."
        elif payout_ratio == 10:
            result_message = f"🎉 JACKPOT!!! {interaction.user} bet {bet_amount:,} como and wins **{payout:,} como**!!! 🎉\n {interaction.user} now has {user_data.balance:,} como."
        elif payout_ratio == 2:
            result_message = f"🎉 {interaction.user} bet {bet_amount:,} como and wins **{payout:,} como**! 🎉\n {interaction.user} now has {user_data.balance:,} como."
        else: 
            result_message = f"😢 {interaction.user} bet {bet_amount:,} como and lost, leaving them with {user_data.balance:,} como... Better luck next time..."
        
        embed.add_field(name="Result", value=result_message, inline=False)

        await interaction.followup.send(content=f"{interaction.user.mention}", embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
    
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

async def setup(bot: Bot): 
    await bot.add_cog(EconomyPlugin(bot))