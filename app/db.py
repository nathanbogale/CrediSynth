import os
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import JSONB


logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    analysis_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32))  # created | completed | failed

    request_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    response_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_text: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


_engine: Optional[object] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def _get_database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


def _ensure_async_driver(url: str) -> str:
    """Normalize Postgres URLs to use asyncpg driver for async engine.

    Converts urls like:
      - postgresql://...
      - postgres://...
      - postgresql+psycopg2://...
    into:
      - postgresql+asyncpg://...
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + url[len("postgresql+psycopg2://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


async def init_db() -> None:
    """Initialize async engine and create tables if DATABASE_URL is provided."""
    global _engine, _sessionmaker
    db_url = _get_database_url()
    if not db_url:
        logger.info("DATABASE_URL not set; auditing disabled")
        return
    db_url = _ensure_async_driver(db_url)
    # Ensure target database exists (connect via admin DB 'postgres')
    await _ensure_database_exists(db_url)
    _engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized and tables ensured")


def has_db() -> bool:
    return _sessionmaker is not None


async def audit_created(analysis_id: str, correlation_id: Optional[str], request_json: dict) -> None:
    if not has_db():
        return
    async with _sessionmaker() as session:
        rec = AnalysisRecord(
            analysis_id=analysis_id,
            correlation_id=correlation_id,
            status="created",
            request_json=request_json,
        )
        session.add(rec)
        await session.commit()


async def audit_completed(analysis_id: str, response_json: dict) -> None:
    if not has_db():
        return
    async with _sessionmaker() as session:
        rec = await session.get(AnalysisRecord, analysis_id)
        if rec:
            rec.status = "completed"
            rec.response_json = response_json
            rec.completed_at = datetime.utcnow()
            await session.commit()


async def audit_failed(analysis_id: str, error_text: str) -> None:
    if not has_db():
        return
    async with _sessionmaker() as session:
        rec = await session.get(AnalysisRecord, analysis_id)
        if rec:
            rec.status = "failed"
            rec.error_text = error_text[:2048]
            rec.completed_at = datetime.utcnow()
            await session.commit()


def _admin_url_from(db_url: str) -> tuple[str, str]:
    """Return (admin_url, target_db_name) for a postgres DATABASE_URL."""
    # Expect format: postgresql+asyncpg://user:pass@host:port/dbname
    # Extract db name from the last path segment
    if "postgresql" not in db_url:
        return db_url, ""
    parts = db_url.rsplit("/", 1)
    if len(parts) == 2:
        base, dbname = parts
    else:
        base, dbname = db_url, ""
    # Replace db with 'postgres' for admin connection
    admin = f"{base}/postgres"
    return admin, dbname


async def _ensure_database_exists(db_url: str) -> None:
    """Create database if it does not exist. Requires privileges on server.

    This runs against the admin database 'postgres' and issues CREATE DATABASE
    in AUTOCOMMIT mode if the target database is missing.
    """
    if "postgresql" not in db_url:
        # Only for Postgres; other backends not supported here
        return
    # Ensure async driver for admin connection too
    admin_url, target_db = _admin_url_from(_ensure_async_driver(db_url))
    if not target_db:
        return
    admin_engine = create_async_engine(admin_url, echo=False, pool_pre_ping=True)
    async with admin_engine.connect() as conn:
        # Check existence
        rs = await conn.exec_driver_sql(
            "SELECT 1 FROM pg_database WHERE datname = :dname",
            {"dname": target_db},
        )
        exists = rs.scalar() is not None
        if not exists:
            # CREATE DATABASE cannot run inside a transaction; use AUTOCOMMIT
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            try:
                await conn.exec_driver_sql(f'CREATE DATABASE "{target_db}"')
                logger.info(f"Created database '{target_db}'")
            except Exception as e:
                # If creation fails due to duplication or permissions, log and proceed
                logger.warning(f"CREATE DATABASE failed (may already exist or insufficient privileges): {e}")
    await admin_engine.dispose()