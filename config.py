from __future__ import annotations
from typing import Final
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN: Final = os.getenv("TOKEN")