"""Load demo data into MongoDB. Run from backend/: python scripts/seed.py"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")


async def _main() -> None:
    from app.db import close_db, get_client
    from app.seed.demo_data import seed_database

    get_client()
    await seed_database()
    await close_db()
    print("Seed completed.")


if __name__ == "__main__":
    asyncio.run(_main())
