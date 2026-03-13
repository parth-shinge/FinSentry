"""
FinSentry - Database Layer
==============================

SQLAlchemy ORM integration for persisting financial transactions into
PostgreSQL.  Provides:

* ``Base``              — Declarative base for all ORM models.
* ``TransactionRecord`` — Table mapping for ingested transactions.
* ``get_engine()``      — Engine factory with connection-pool settings.
* ``SessionLocal``      — Scoped session factory.
* ``get_session()``     — Context-manager that yields a session and
                          handles commit / rollback automatically.
* ``init_db()``         — Creates all tables defined on ``Base``.

Connection Pooling
------------------
The engine is configured with pool settings suitable for a mid-scale
production workload:

* ``pool_size=10``        — baseline persistent connections
* ``max_overflow=20``     — burst capacity above pool_size
* ``pool_pre_ping=True``  — detect stale connections before use
* ``pool_recycle=3600``   — recycle connections every hour

Usage::

    from ingestion.db import get_session, init_db

    init_db()  # create tables if they don't exist

    with get_session() as session:
        session.add(record)
        # auto-committed on exit, rolled back on exception
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from utils.config import settings
from utils.logging import get_logger

logger = get_logger("ingestion.db")

# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------
Base = declarative_base()


# ---------------------------------------------------------------------------
# ORM Model — TransactionRecord
# ---------------------------------------------------------------------------


class TransactionRecord(Base):
    """SQLAlchemy ORM model for the ``transactions`` table.

    Every ingested and normalized transaction is persisted as a row in
    this table.  The ``created_at`` column is populated automatically at
    insert time.

    Columns:
        id:                  Auto-incrementing primary key.
        transaction_id:      Upstream transaction identifier (unique).
        account_id:          Originating account.
        sender_entity_id:    Entity ID of the sender.
        receiver_entity_id:  Entity ID of the receiver.
        amount:              Monetary value.
        currency:            ISO 4217 currency code (uppercased).
        timestamp:           UTC datetime of the transaction.
        origin_country:      ISO 3166-1 alpha-2 origin.
        destination_country: ISO 3166-1 alpha-2 destination.
        merchant_category:   Merchant category code / description.
        transaction_type:    Transaction type (wire, ACH, card, …).
        channel:             Channel (online, branch, ATM, mobile).
        is_international:    Whether the transaction crosses borders.
        risk_flag:           Optional upstream risk label.
        created_at:          Row insertion timestamp (UTC).
    """

    __tablename__ = "transactions"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id: str = Column(String(64), unique=True, nullable=False, index=True)
    account_id: str = Column(String(64), nullable=False, index=True)
    sender_entity_id: str = Column(String(64), nullable=False, index=True)
    receiver_entity_id: str = Column(String(64), nullable=False, index=True)
    amount: float = Column(Float, nullable=False)
    currency: str = Column(String(8), nullable=False)
    timestamp: datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    origin_country: str = Column(String(4), nullable=False)
    destination_country: str = Column(String(4), nullable=False)
    merchant_category: str = Column(String(64), nullable=False)
    transaction_type: str = Column(String(32), nullable=False)
    channel: str = Column(String(32), nullable=False)
    is_international: bool = Column(Boolean, nullable=False, default=False)
    risk_flag: str | None = Column(String(32), nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<TransactionRecord(id={self.id}, "
            f"txn={self.transaction_id}, "
            f"amount={self.amount} {self.currency})>"
        )


# ---------------------------------------------------------------------------
# Engine & Session Factory
# ---------------------------------------------------------------------------

_engine = None


def get_engine(database_url: str | None = None):
    """Create or return the singleton SQLAlchemy engine.

    Args:
        database_url: Override the connection string from settings.
                      Useful for testing with SQLite.

    Returns:
        A :class:`sqlalchemy.engine.Engine` instance with connection
        pooling configured.
    """
    global _engine  # noqa: WPS420
    if _engine is None:
        url = database_url or settings.DATABASE_URL
        # SQLite does not support pool_size / max_overflow
        is_sqlite = url.startswith("sqlite")
        pool_kwargs = (
            {}
            if is_sqlite
            else {
                "pool_size": 10,
                "max_overflow": 20,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
            }
        )
        _engine = create_engine(url, echo=False, **pool_kwargs)
        logger.info("Database engine created for %s", url.split("@")[-1] if "@" in url else url)
    return _engine


def reset_engine() -> None:
    """Dispose of the current engine (used in tests to switch databases)."""
    global _engine  # noqa: WPS420
    if _engine is not None:
        _engine.dispose()
        _engine = None


def _get_session_factory(engine=None) -> sessionmaker:
    """Return a sessionmaker bound to the given (or default) engine."""
    return sessionmaker(
        bind=engine or get_engine(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def get_session(engine=None) -> Generator[Session, None, None]:
    """Context-managed database session with auto commit / rollback.

    Usage::

        with get_session() as session:
            session.add(record)
            # committed on clean exit
            # rolled back on exception

    Args:
        engine: Optional engine override (useful for tests).

    Yields:
        An active :class:`sqlalchemy.orm.Session`.
    """
    factory = _get_session_factory(engine)
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Session rolled back due to error")
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Database Initialization
# ---------------------------------------------------------------------------


def init_db(engine=None) -> None:
    """Create all tables defined on :data:`Base` if they do not exist.

    Args:
        engine: Optional engine override.  When ``None`` the default
                engine derived from ``settings.DATABASE_URL`` is used.

    This is safe to call multiple times — existing tables are not dropped.
    """
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)
    logger.info("Database tables created / verified")
