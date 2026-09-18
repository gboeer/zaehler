import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from zaehler.models import Base

# Datenbank liegt im data/-Verzeichnis neben dem Projektroot
_DB_DIR = Path(__file__).parent.parent.parent / "data"
_DB_DIR.mkdir(exist_ok=True)
_DB_PATH = _DB_DIR / "zaehler.db"

_BACKUP_DIR = _DB_DIR / "backups"
_MAX_BACKUPS = 30

_engine = None
_SessionLocal = None


def _unique_backup_path() -> Path:
    """Erzeugt einen freien Backup-Dateinamen (mit Zähler-Suffix bei Kollision)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = _BACKUP_DIR / f"zaehler_{timestamp}.db"
    suffix = 1
    while backup_path.exists():
        backup_path = _BACKUP_DIR / f"zaehler_{timestamp}_{suffix}.db"
        suffix += 1
    return backup_path


def _prune_backups():
    backups = sorted(_BACKUP_DIR.glob("zaehler_*.db"))
    for old_backup in backups[:-_MAX_BACKUPS]:
        old_backup.unlink()


def _backup_database():
    """Sichert die bestehende Datenbankdatei vor dem Start, behält die letzten _MAX_BACKUPS Kopien."""
    if not _DB_PATH.exists():
        return

    _BACKUP_DIR.mkdir(exist_ok=True)
    shutil.copy2(_DB_PATH, _unique_backup_path())
    _prune_backups()


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

        # meters-Tabelle
        meters_cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(meters)")).fetchall()
        }
        if "parent_id" not in meters_cols:
            conn.execute(text("ALTER TABLE meters ADD COLUMN parent_id INTEGER REFERENCES meters(id)"))

        conn.commit()


def get_engine():
    global _engine
    if _engine is None:
        _backup_database()
        _engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False)
        Base.metadata.create_all(_engine)
        _migrate(_engine)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def get_db_path() -> Path:
    """Pfad zur aktiven Datenbankdatei."""
    return _DB_PATH


def get_backup_dir() -> Path:
    """Verzeichnis, in dem automatische Backups abgelegt werden."""
    _BACKUP_DIR.mkdir(exist_ok=True)
    return _BACKUP_DIR


def create_manual_backup() -> Path:
    """Erstellt sofort ein Backup der aktuellen Datenbankdatei und gibt den Pfad zurück."""
    _BACKUP_DIR.mkdir(exist_ok=True)
    backup_path = _unique_backup_path()
    shutil.copy2(_DB_PATH, backup_path)
    _prune_backups()
    return backup_path
