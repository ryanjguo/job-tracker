from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    kwargs = {}
    if url.startswith("sqlite"):
        # FastAPI runs sync endpoints in a threadpool
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(bind=None) -> None:
    from . import models  # noqa: F401  (registers tables)

    bind = bind or engine
    Base.metadata.create_all(bind=bind)
    added = add_missing_columns(bind)
    if any(t == "applications" for t, _ in added):
        from .importer import backfill_fields_from_notes

        backfill_fields_from_notes(bind)


def add_missing_columns(bind) -> list[tuple[str, str]]:
    """A tiny stand-in for migrations: create_all() never alters existing tables, so add any
    column the models have but the database doesn't. New columns must be nullable or have a
    server_default. Returns the (table, column) pairs it added."""
    added: list[tuple[str, str]] = []
    insp = inspect(bind)
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(dialect=bind.dialect)}'
                if col.server_default is not None:
                    ddl += f" DEFAULT '{col.server_default.arg}'" + ("" if col.nullable else " NOT NULL")
                elif not col.nullable:
                    raise RuntimeError(f"{table.name}.{col.name} needs a server_default to be added")
                conn.execute(text(ddl))
                added.append((table.name, col.name))
    return added


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
