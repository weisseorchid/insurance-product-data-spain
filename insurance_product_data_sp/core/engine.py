"""SQLModel engine and session helpers."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

_engine = None


class DatabaseNotFoundError(FileNotFoundError):
    """Raised when the bundled database file is not found."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        super().__init__(
            f"Bundled database not found at: {db_path}\n"
            "This usually means the package was not installed correctly.\n"
            "Try reinstalling: pip install --force-reinstall insurance-product-data-sp"
        )


def get_database_path() -> Path:
    """Return the path to the bundled SQLite database."""
    return Path(__file__).parent.parent / "data" / "insurance.db"


def get_engine():
    """Return a singleton SQLAlchemy engine.

    Raises:
        DatabaseNotFoundError: If the bundled database file does not exist.
    """
    global _engine
    if _engine is None:
        db_path = get_database_path()
        if not db_path.exists():
            raise DatabaseNotFoundError(db_path)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_session() -> Session:
    """Create a session for database operations."""
    return Session(get_engine())


def init_database(db_path: Path | None = None) -> None:
    """Initialize the database schema for a given path."""
    if db_path is None:
        engine = get_engine()
    else:
        engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
