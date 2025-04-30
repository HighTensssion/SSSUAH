from __future__ import annotations

import discord
from tortoise.models import Model
from tortoise import fields

__all__ = ("AfkModel", "EconomyModel", "ObjektModel", "CollectionModel", "CooldownModel", "ShopModel", "PityModel")

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

class ObjektModel(Model):
    id: int = fields.IntField(pk=True)
    slug: str = fields.TextField(null=True)
    objekt_name: str = fields.TextField()
    season: str | None = fields.TextField(null=True)
    member: str | None = fields.TextField(null=True)
    series: str | None = fields.TextField(null=True)
    class_: str | None = fields.TextField(null=True, source_field="class")
    image_url: str | None = fields.TextField(null=True)
    background_color: str | None = fields.TextField(null=True)
    rarity: int = fields.BigIntField(default=1)

    class Meta:
        table = "objekts"

class CollectionModel(Model):
    id: int = fields.IntField(pk=True)
    user_id: str = fields.TextField()
    objekt: fields.ForeignKeyRelation["ObjektModel"] = fields.ForeignKeyField(
        "models.ObjektModel", related_name="collections", on_delete=fields.CASCADE
    )
    copies: int = fields.IntField(default=1)
    created_at = fields.DatetimeField(auto_now=True)
    updated_at = fields.DatetimeField(auto_now_add=True)
    class Meta:
        table = "collections"
        unique_together = ("user_id", "objekt")

class CooldownModel(Model):
    id: int = fields.IntField(pk=True)
    user_id: str = fields.TextField()
    command: str = fields.TextField()
    expires_at = fields.DatetimeField(null=True)

    class Meta:
        table = "cooldowns"
        unique_together = ("user_id", "command")

class ShopModel(Model):
    id: int = fields.IntField(pk=True)
    objekt = fields.ForeignKeyField("models.ObjektModel", relate_name="shop_items", on_delete=fields.CASCADE)
    price: int = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True)
    last_refreshed = fields.DatetimeField(null=True)

    class Meta:
        table = "shop"
    
class PityModel(Model):
    user_id = fields.CharField(max_length=50, unique=True)
    pity_count = fields.IntField(default=0)
    last_reset = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "pity"