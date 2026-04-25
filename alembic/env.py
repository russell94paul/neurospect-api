from logging.config import fileConfig

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import engine_from_config, pool

from alembic import context

# Load model metadata so Alembic can detect schema changes
from app.models.base import Base  # noqa: F401 — registers metadata
import app.models.user  # noqa: F401
import app.models.trade  # noqa: F401
import app.models.screenshot  # noqa: F401
import app.models.tv_token  # noqa: F401
import app.models.coaching_event  # noqa: F401
from app.config import settings as app_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", app_settings.sync_database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
