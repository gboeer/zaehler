from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from zaehler.models import Base

# Datenbank liegt im data/-Verzeichnis neben dem Projektroot
_DB_DIR = Path(__file__).parent.parent.parent / "data"
_DB_DIR.mkdir(exist_ok=True)
_DB_PATH = _DB_DIR / "zaehler.db"

_engine = None
_SessionLocal = None


def _migrate(engine):
    """Fügt neue Spalten hinzu, falls sie noch nicht existieren (SQLite ALTER TABLE)."""
    with engine.connect() as conn:
        from sqlalchemy import text
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(prices)")).fetchall()
        }
        for col, definition in [
            ("brennwert", "FLOAT"),
            ("z_zahl", "FLOAT"),
        ]:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE prices ADD COLUMN {col} {definition}"))
        conn.commit()


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False)
        Base.metadata.create_all(_engine)
        _migrate(_engine)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()
