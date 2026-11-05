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
        pytest.fail('requires disposable PostgreSQL TEST_DATABASE_URL')
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


@pytest.fixture
async def closure_sync_url(async_engine):
    return async_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest.fixture
async def seed(async_engine):
    from types import SimpleNamespace
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from controlplane_db.models import Role, Tenant
    ta, tb, ra, rb = [uuid.uuid4() for _ in range(4)]
    async with async_sessionmaker(async_engine)() as session:
        session.add_all([Tenant(id=ta, name=str(ta), is_active=True), Tenant(id=tb, name=str(tb), is_active=True)])
        await session.flush()
        session.add_all([Role(id=ra, tenant_id=ta, name="admin", permissions=[]), Role(id=rb, tenant_id=tb, name="admin", permissions=[])])
        await session.commit()
    return SimpleNamespace(ta=ta,tb=tb,ra=ra,rb=rb)


@pytest.fixture
def migration_database():
    raw = os.environ.get('TEST_DATABASE_URL')
    if not raw:
        pytest.fail('requires disposable PostgreSQL TEST_DATABASE_URL')
    base = make_url(raw).set(drivername='postgresql+psycopg')
    admin = create_engine(base, isolation_level='AUTOCOMMIT')
    created = []
    def make():
        name = 'tenancy_ahead_' + uuid.uuid4().hex
        with admin.connect() as cx:
            cx.execute(text(f'CREATE DATABASE "{name}"'))
        created.append(name)
        return base.set(database=name).render_as_string(hide_password=False)
    try:
        yield make
    finally:
        with admin.connect() as cx:
            for name in created:
                cx.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def pytest_configure(config):
    config.addinivalue_line('markers', 'integration: disposable PostgreSQL owner integration')
