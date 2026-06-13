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
    if "calls" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("calls")}
    additions = {
        "severity": "VARCHAR DEFAULT 'non-urgent'",
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
