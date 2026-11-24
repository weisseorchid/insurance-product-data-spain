"""SQLModel engine and session helpers."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

_engine = None
_custom_db_path: Path | None = None


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
    if _custom_db_path is not None:
        return _custom_db_path
    return Path(__file__).parent.parent / "data" / "insurance.db"


def set_database_path(path: Path | None) -> None:
    """Set a custom database path (for testing). Pass None to restore default."""
    global _custom_db_path, _engine
    _custom_db_path = path
    _engine = None  # Force engine recreation on next get_engine()


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

        # Open bundled DB read-only to prevent WAL file creation during tests
        # Test DBs (via set_database_path) need write access for fixture setup
        is_bundled_db = _custom_db_path is None
        if is_bundled_db:
            # Use file: URI with mode=ro for read-only access
            db_uri = f"sqlite:///file:{db_path}?mode=ro&uri=true"
            connect_args = {"check_same_thread": False, "uri": True}
        else:
            db_uri = f"sqlite:///{db_path}"
            connect_args = {"check_same_thread": False}

        _engine = create_engine(
            db_uri,
            echo=False,
            connect_args=connect_args,
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
