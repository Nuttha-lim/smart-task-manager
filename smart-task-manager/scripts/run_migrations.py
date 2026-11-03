"""Run alembic migrations programmatically.
Usage: python scripts\run_migrations.py
"""
import os
import sys
from alembic.config import Config
from alembic import command
import sqlalchemy

here = os.path.dirname(os.path.dirname(__file__))
alembic_ini = os.path.join(here, 'alembic.ini')
cfg = Config(alembic_ini)
cfg.set_main_option('script_location', os.path.join(here, 'alembic'))

# ensure project package modules are importable (scripts/ is a child of project)
sys.path.insert(0, here)
from database import engine


def main():
    # check whether any application tables already exist
    with engine.connect() as conn:
        inspector = sqlalchemy.inspect(conn)
        existing = inspector.get_table_names()

    if existing:
        print('Detected existing tables in DB, stamping alembic head (no SQL will be run).')
        command.stamp(cfg, 'head')
    else:
        print('No tables detected, running alembic upgrade to create schema.')
        command.upgrade(cfg, 'head')


if __name__ == '__main__':
    main()
