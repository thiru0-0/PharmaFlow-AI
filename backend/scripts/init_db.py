"""Create all tables + install DB-level state-machine guards, then seed demo data.

Usage:
    python -m scripts.init_db          # create + guards + seed
    python -m scripts.init_db --no-seed
"""
from __future__ import annotations

import sys

from app.db.base import Base, engine, SessionLocal
import app.models  # noqa: F401
from app.db.guards import install_guards
from app.services.demo import seed


def main() -> None:
    Base.metadata.create_all(bind=engine)
    install_guards(engine)
    print("tables created + guards installed")
    if "--no-seed" not in sys.argv:
        db = SessionLocal()
        try:
            result = seed(db)
            print(f"seeded {len(result['accounts'])} accounts, {len(result['batches'])} batches")
            for k, v in result["batches"].items():
                print(f"  {k}: {v}")
        finally:
            db.close()


if __name__ == "__main__":
    main()
