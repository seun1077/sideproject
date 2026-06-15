from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from .paths import PROCESSED


def utc_cutoff(days: int) -> str:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


def cleanup_processed_files(
    processed_dir: Path = PROCESSED,
    keep_days: int = 7,
    apply: bool = False,
) -> dict:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=keep_days)
    candidates: list[Path] = []
    if processed_dir.exists():
        for path in processed_dir.iterdir():
            if not path.is_file() or path.suffix.lower() not in {".csv", ".json"}:
                continue
            modified_at = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
            if modified_at < cutoff:
                candidates.append(path)

    total_bytes = sum(path.stat().st_size for path in candidates if path.exists())
    if apply:
        for path in candidates:
            path.unlink(missing_ok=True)

    return {
        "processed_dir": str(processed_dir),
        "keep_days": keep_days,
        "matched_files": len(candidates),
        "matched_bytes": total_bytes,
        "deleted_files": len(candidates) if apply else 0,
        "deleted_bytes": total_bytes if apply else 0,
        "dry_run": not apply,
    }


def prune_price_snapshots(
    conn: sqlite3.Connection,
    keep_days: int = 180,
    apply: bool = False,
) -> dict:
    cutoff = utc_cutoff(keep_days)
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM price_snapshots WHERE collected_at < ?",
        (cutoff,),
    ).fetchone()
    matched = int(row["count"] if row else 0)

    if apply and matched:
        with conn:
            conn.execute("DELETE FROM price_snapshots WHERE collected_at < ?", (cutoff,))

    return {
        "table": "price_snapshots",
        "keep_days": keep_days,
        "cutoff": cutoff,
        "matched_rows": matched,
        "deleted_rows": matched if apply else 0,
        "dry_run": not apply,
    }

