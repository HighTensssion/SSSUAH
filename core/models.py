from __future__ import annotations

import discord
from tortoise.models import Model
from tortoise import fields

__all__ = ("EconomyModel", "ObjektModel", "CollectionModel", "CooldownModel", "ShopModel", "PityModel", "TriviaSessionModel", "TriviaStatsModel")

class EconomyModel(Model):
    id: int = fields.BigIntField(pk=True, unique=True)
    balance: int = fields.BigIntField(default=100)
    created_at = fields.DatetimeField(auto_now=True)
    updated_at = fields.DatetimeField(auto_now_add=True)

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
    front_media: str | None = fields.TextField(null=True)

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
    user_id = fields.BigIntField()
    objekt = fields.ForeignKeyField("models.ObjektModel", relate_name="shop_items", on_delete=fields.CASCADE)
    price: int = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "shop"
    
class PityModel(Model):
    user_id = fields.CharField(max_length=50, unique=True)
    pity_count = fields.IntField(default=0)
    chase_objekt_slug = fields.CharField(max_length=100, null=True)
    chase_pity_count = fields.IntField(default=0)
    last_reset = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "pity"

class TriviaSessionModel(Model):
    id = fields.IntField(pk=True)
    channel_id = fields.BigIntField()
    user_id = fields.BigIntField()
    question_index = fields.IntField()
    started_at = fields.DatetimeField(auto_now_add=True)
    is_active = fields.BooleanField(default=True)

class TriviaStatsModel(Model):
    id = fields.IntField(pk=True)
    user_id = fields.BigIntField(unique=True)
    correct = fields.IntField(default=0)
    total = fields.IntField(default=0)
    streak = fields.IntField(default=0)
    last_played = fields.DatetimeField(null=True)