from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_columns()


def _migrate_sqlite_columns() -> None:
    """Add any columns introduced after the table already existed (sqlite demo db)."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    # Columns added to `calls` after the table already existed (sqlite demo db).
    if "calls" in tables:
        existing = {col["name"] for col in inspector.get_columns("calls")}
        additions = {
            "channel": "VARCHAR DEFAULT 'voicemail'",
            "no_callback": "BOOLEAN DEFAULT 0",
            "insufficient_detail": "BOOLEAN DEFAULT 0",
            "severity": "VARCHAR DEFAULT 'fyi'",
            "patient_name": "VARCHAR DEFAULT 'Unknown'",
            "room": "VARCHAR DEFAULT ''",
            "caller_name": "VARCHAR DEFAULT ''",
            "caller_role": "VARCHAR DEFAULT ''",
            "resolved": "BOOLEAN DEFAULT 0",
        }
        with engine.begin() as conn:
            for column, ddl in additions.items():
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE calls ADD COLUMN {column} {ddl}"))

    # Columns added to `devices` after the table already existed. The table
    # itself is created by Base.metadata.create_all(); this only backfills
    # columns on a pre-existing devices table (repo migration convention).
    if "devices" in tables:
        existing = {col["name"] for col in inspector.get_columns("devices")}
        additions = {
            "platform": "VARCHAR DEFAULT 'ios'",
            "created_at": "DATETIME",
            "last_seen_at": "DATETIME",
        }
        with engine.begin() as conn:
            for column, ddl in additions.items():
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE devices ADD COLUMN {column} {ddl}"))
