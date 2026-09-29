from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from app.config import settings
from app.db import Base, make_engine


def test_migration_roundtrip_and_postgres_ddl(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "migrations.db"}'
    monkeypatch.setattr(settings(), 'database_url', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
    command.upgrade(config, 'head')
    engine = make_engine(url)
    assert set(Base.metadata.tables).issubset(set(inspect(engine).get_table_names()))
    command.downgrade(config, 'base')
    assert not set(Base.metadata.tables).intersection(inspect(engine).get_table_names())
    command.upgrade(config, 'head')
    engine.dispose()
    # Compile only: this checks dialect portability, not a running PostgreSQL instance.
    for table in Base.metadata.sorted_tables:
        sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert 'CREATE TABLE' in sql
