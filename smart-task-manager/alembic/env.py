import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging (best-effort).
try:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
except Exception:
    # fallback: continue without configuring logging from ini
    pass

# import your model's MetaData object for 'autogenerate'
import database as db_module
import models as models_module

target_metadata = models_module.Base.metadata


def run_migrations_offline():
    url = db_module.DATABASE_URL
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = db_module.engine

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
