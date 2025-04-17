from __future__ import annotations

from typing import Optional, Union, Self

from discord import Colour, Embed as OriginalEmbed

__all__ = (
    "Embed",
)

class Embed(OriginalEmbed):
    def __init__(self, color: Optional[Union[int, Colour]] = Colour.blurple(), **kwargs):
        super().__init__(color=color, **kwargs)

    def credit(self) -> Self:
        super().set_footer(text="Made with love by the GNDSG")
        return self