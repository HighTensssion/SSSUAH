from __future__ import annotations

import discord
from tortoise.models import Model
from tortoise import fields

__all__ = ("AfkModel", "Economy Model")

class AfkModel(Model):
    id = fields.BigIntField(pk=True, unique=True)
    guild_id = fields.BigIntField()
    reason = fields.CharField(max_length=1000)
    since = fields.DatetimeField(auto_now=True)

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"
    
    @property
    def formatted_since(self) -> str:
        return discord.utils.format_dt(self.since)
    
    class Meta:
        table = "afks"

class EconomyModel(Model):
    id: int = fields.BigIntField(pk=True, unique=True)
    balance: int = fields.BigIntField(default=100)
    created_at = fields.DatetimeField(auto_now=True)

    class Meta: table = "economy"