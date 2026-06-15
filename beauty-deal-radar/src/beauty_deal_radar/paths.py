from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
DB_PATH = DATA / "beauty_deals.sqlite3"
SEEDS = DATA / "seeds.csv"
MIGRATIONS = ROOT / "migrations"

