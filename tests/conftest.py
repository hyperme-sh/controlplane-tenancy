"""Directory integration uses a newly created disposable database per case."""
import os
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from controlplane_db import migrations


@pytest_asyncio.fixture
async def async_engine():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('requires disposable PostgreSQL TEST_DATABASE_URL')
    base = make_url(url).set(drivername='postgresql+psycopg')
    name = 'tenancy_test_' + uuid.uuid4().hex
    admin = create_engine(base, isolation_level='AUTOCOMMIT')
    engine = None
    try:
        with admin.connect() as cx:
            cx.execute(text(f'CREATE DATABASE "{name}"'))
        target = base.set(database=name)
        migrations.upgrade(target.render_as_string(hide_password=False), chains=['platform'])
        engine = create_async_engine(target.set(drivername='postgresql+asyncpg'))
        yield engine
    finally:
        if engine is not None:
            await engine.dispose()
        with admin.connect() as cx:
            cx.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
