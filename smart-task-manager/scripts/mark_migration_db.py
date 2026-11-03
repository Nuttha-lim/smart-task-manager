"""Mark the database as having applied the initial migration by writing
the alembic_version row directly. Use when tables already exist.
"""
from database import engine

create_sql = '''
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL
);
'''

with engine.connect() as conn:
    conn.execute(create_sql)
    conn.execute("DELETE FROM alembic_version")
    conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0001_initial')")
    conn.commit()

print('alembic_version set to 0001_initial')
