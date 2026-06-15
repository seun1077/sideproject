from __future__ import annotations

import csv
from pathlib import Path

from .models import ProductSeed
from .paths import SEEDS


def read_seeds(path: Path = SEEDS) -> list[ProductSeed]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [
            ProductSeed(
                brand=row["brand"].strip(),
                product=row["product"].strip(),
                query=row["query"].strip(),
                category=row["category"].strip(),
                volume_hint=row["volume_hint"].strip(),
            )
            for row in csv.DictReader(f)
        ]

