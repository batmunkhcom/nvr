"""Cleanup old events and object counters.

Usage (from API container):
    python /app/cleanup.py --before 2026-07-01

Deletes:
- events older than --before date
- object_counters older than --before date
- snapshot files referenced by deleted events
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://nvr_user:nvr_dev_password_change_me@nvr-db/nvr",
)

SNAPSHOT_DIR = os.environ.get("STORAGE_LOCAL_PATH", "/data/recordings") + "/snapshots"

DRY_RUN = False


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


async def _get_counts(db: AsyncSession, before: date) -> tuple[int, int]:
    """Count events and counter rows older than before."""
    event_row = await db.execute(
        text("SELECT COUNT(*) FROM events WHERE created_at < :before"),
        {"before": before},
    )
    counter_row = await db.execute(
        text("SELECT COUNT(*) FROM object_counters WHERE counter_date < :before"),
        {"before": before},
    )
    return event_row.scalar() or 0, counter_row.scalar() or 0


async def _get_snapshot_paths(db: AsyncSession, before: date) -> list[str]:
    """Get snapshot file paths for events older than before."""
    rows = await db.execute(
        text(
            "SELECT snapshot_path FROM events "
            "WHERE created_at < :before AND snapshot_path IS NOT NULL"
        ),
        {"before": before},
    )
    return [r[0] for r in rows.fetchall() if r[0]]


async def _delete_events(db: AsyncSession, before: date) -> int:
    """Delete events and return count."""
    result = await db.execute(
        text("DELETE FROM events WHERE created_at < :before"),
        {"before": before},
    )
    return result.rowcount or 0


async def _delete_counters(db: AsyncSession, before: date) -> int:
    """Delete object counters and return count."""
    result = await db.execute(
        text("DELETE FROM object_counters WHERE counter_date < :before"),
        {"before": before},
    )
    return result.rowcount or 0


async def cleanup(before: date, dry_run: bool = False) -> None:
    engine = create_async_engine(DB_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        event_count, counter_count = await _get_counts(db, before)
        snapshot_paths = await _get_snapshot_paths(db, before)

    print(f"Clean-up before: {_bold(str(before))}")
    print(f"  Events to delete:   {_bold(str(event_count))}")
    print(f"  Counters to delete:  {_bold(str(counter_count))}")
    print(f"  Snapshots to unlink: {_bold(str(len(snapshot_paths)))}")

    if dry_run:
        print(f"\n  ({_bold('dry run')} — no changes made)")
        return

    if event_count == 0 and counter_count == 0:
        print("\n  Nothing to delete.")
        return

    confirm = input(f"\nDelete {event_count + counter_count} rows + {len(snapshot_paths)} files? [y/N] ")
    if confirm.lower() != "y":
        print("  Aborted.")
        return

    async with async_session() as db:
        async with db.begin():
            del_events = await _delete_events(db, before)
            del_counters = await _delete_counters(db, before)

    removed_files = 0
    for path in snapshot_paths:
        try:
            if os.path.exists(path):
                os.unlink(path)
                removed_files += 1
        except OSError:
            pass

    print(f"\n  Deleted:")
    print(f"    {_bold(str(del_events))} events")
    print(f"    {_bold(str(del_counters))} counter rows")
    print(f"    {_bold(str(removed_files))} snapshot files")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup old events and object counters")
    parser.add_argument(
        "--before",
        required=True,
        help="Delete records older than this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without deleting",
    )
    args = parser.parse_args()

    try:
        before = date.fromisoformat(args.before)
    except ValueError:
        print(f"Invalid date: {args.before}. Use YYYY-MM-DD format.")
        return

    asyncio.run(cleanup(before, args.dry_run))


if __name__ == "__main__":
    main()
