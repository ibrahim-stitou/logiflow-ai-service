"""Environnement Alembic : URL issue de Settings, table de versions dans le schéma `copilote`."""

from alembic import context
from sqlalchemy import create_engine, text

from logiflow_ai_service.config import get_settings
from logiflow_ai_service.infrastructure.persistence.models import SCHEMA, Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_schema=SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        # Le schéma est normalement créé par docker/postgres/init/02-ai-database.sql ; on le
        # garantit ici pour une base créée à la main.
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=SCHEMA,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
