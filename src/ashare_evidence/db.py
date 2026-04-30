from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DB_PATH = Path("data/ashare_dashboard.db")
DEFAULT_DB_URL = f"sqlite:///{DEFAULT_DB_PATH}"

_ENGINE_CACHE: dict[str, Engine] = {}
_SESSION_FACTORY_CACHE: dict[str, sessionmaker[Session]] = {}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def align_datetime_timezone(value: datetime | None, *, reference: datetime) -> datetime | None:
    if value is None:
        return None
    if reference.tzinfo is None:
        return value.replace(tzinfo=None) if value.tzinfo is not None else value
    if value.tzinfo is None:
        return value.replace(tzinfo=reference.tzinfo)
    return value.astimezone(reference.tzinfo)


def get_database_url(explicit: str | None = None) -> str:
    return explicit or os.getenv("ASHARE_DATABASE_URL") or DEFAULT_DB_URL


def _prepare_sqlite_parent(database_url: str) -> None:
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        db_path = Path(database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str | None = None) -> Engine:
    resolved = get_database_url(database_url)
    engine = _ENGINE_CACHE.get(resolved)
    if engine is None:
        _prepare_sqlite_parent(resolved)
        connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
        engine = create_engine(resolved, future=True, connect_args=connect_args)
        _ENGINE_CACHE[resolved] = engine
    return engine


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    resolved = get_database_url(database_url)
    factory = _SESSION_FACTORY_CACHE.get(resolved)
    if factory is None:
        factory = sessionmaker(bind=get_engine(resolved), autoflush=False, autocommit=False, expire_on_commit=False)
        _SESSION_FACTORY_CACHE[resolved] = factory
    return factory


def init_database(database_url: str | None = None) -> Engine:
    from ashare_evidence import models  # noqa: F401
    from ashare_evidence.account_space import ROOT_ACCOUNT_LOGIN
    from ashare_evidence.models import AccountSpace, AppSetting, SimulationEvent, SimulationSession, WatchlistEntry, WatchlistFollow

    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    _run_schema_migrations(engine)
    with Session(engine) as session:
        marker = session.scalar(select(AppSetting).where(AppSetting.setting_key == "multi_account_isolation_v1_migration"))
        if marker is None:
            now = utcnow()
            root_space = session.get(AccountSpace, ROOT_ACCOUNT_LOGIN)
            if root_space is None:
                session.add(
                    AccountSpace(
                        account_login=ROOT_ACCOUNT_LOGIN,
                        role_snapshot="root",
                        first_seen_at=now,
                        last_seen_at=now,
                        last_acted_at=now,
                        created_by_root=False,
                        metadata_payload={"migration": "multi_account_isolation_v1"},
                    )
                )
            for entry in session.scalars(select(WatchlistEntry)).all():
                existing = session.scalar(
                    select(WatchlistFollow).where(
                        WatchlistFollow.account_login == ROOT_ACCOUNT_LOGIN,
                        WatchlistFollow.symbol == entry.symbol,
                    )
                )
                if existing is not None:
                    continue
                removed_at = entry.updated_at if entry.status != "active" else None
                session.add(
                    WatchlistFollow(
                        account_login=ROOT_ACCOUNT_LOGIN,
                        symbol=entry.symbol,
                        status=entry.status,
                        source_kind=entry.source_kind,
                        added_at=entry.created_at,
                        removed_at=removed_at,
                        last_actor_login=ROOT_ACCOUNT_LOGIN,
                        follow_payload={"migrated_from_watchlist_entries": True},
                        created_at=entry.created_at,
                        updated_at=entry.updated_at,
                    )
                )
            session.execute(
                text(
                    "UPDATE simulation_sessions SET owner_login = COALESCE(owner_login, :root) "
                    "WHERE owner_login IS NULL OR owner_login = ''"
                ),
                {"root": ROOT_ACCOUNT_LOGIN},
            )
            session.execute(
                text(
                    "UPDATE paper_portfolios SET owner_login = COALESCE(owner_login, :root) "
                    "WHERE owner_login IS NULL OR owner_login = ''"
                ),
                {"root": ROOT_ACCOUNT_LOGIN},
            )
            session.execute(
                text(
                    "UPDATE paper_orders SET owner_login = COALESCE(owner_login, :root), "
                    "actor_login = COALESCE(actor_login, :root) "
                    "WHERE owner_login IS NULL OR owner_login = '' OR actor_login IS NULL OR actor_login = ''"
                ),
                {"root": ROOT_ACCOUNT_LOGIN},
            )
            session.execute(
                text(
                    "UPDATE paper_fills SET owner_login = COALESCE(owner_login, :root), "
                    "actor_login = COALESCE(actor_login, :root) "
                    "WHERE owner_login IS NULL OR owner_login = '' OR actor_login IS NULL OR actor_login = ''"
                ),
                {"root": ROOT_ACCOUNT_LOGIN},
            )
            session.execute(
                text(
                    "UPDATE simulation_events SET owner_login = COALESCE(owner_login, :root), "
                    "actor_login = COALESCE(actor_login, :root) "
                    "WHERE owner_login IS NULL OR owner_login = '' OR actor_login IS NULL OR actor_login = ''"
                ),
                {"root": ROOT_ACCOUNT_LOGIN},
            )
            session.add(
                AppSetting(
                    setting_key="multi_account_isolation_v1_migration",
                    description="Marks the v1 watchlist/simulation account-space migration as applied.",
                    setting_value={"applied_at": now.isoformat(), "root_account_login": ROOT_ACCOUNT_LOGIN},
                )
            )
            session.commit()
    return engine


def _run_schema_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    column_specs = {
        "paper_portfolios": {
            "owner_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
        },
        "paper_orders": {
            "owner_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
            "actor_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
        },
        "paper_fills": {
            "owner_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
            "actor_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
        },
        "simulation_sessions": {
            "owner_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
        },
        "simulation_events": {
            "owner_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
            "actor_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
        },
    }
    for table_name, columns in column_specs.items():
        existing_columns = {item["name"] for item in inspector.get_columns(table_name)}
        for column_name, ddl in columns.items():
            if column_name not in existing_columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_paper_portfolios_owner_login ON paper_portfolios(owner_login)",
        "CREATE INDEX IF NOT EXISTS idx_paper_orders_owner_login ON paper_orders(owner_login)",
        "CREATE INDEX IF NOT EXISTS idx_paper_orders_actor_login ON paper_orders(actor_login)",
        "CREATE INDEX IF NOT EXISTS idx_paper_fills_owner_login ON paper_fills(owner_login)",
        "CREATE INDEX IF NOT EXISTS idx_paper_fills_actor_login ON paper_fills(actor_login)",
        "CREATE INDEX IF NOT EXISTS idx_simulation_sessions_owner_login ON simulation_sessions(owner_login)",
        "CREATE INDEX IF NOT EXISTS idx_simulation_events_owner_login ON simulation_events(owner_login)",
        "CREATE INDEX IF NOT EXISTS idx_simulation_events_actor_login ON simulation_events(actor_login)",
    ]
    with engine.begin() as conn:
        for statement in index_statements:
            conn.execute(text(statement))


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    session = get_session_factory(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
