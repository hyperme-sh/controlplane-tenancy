"""Retained marketplace startup cases from Panopticon owner-chain integration."""
from importlib.resources import files
import uuid
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from controlplane_db.base import Base
import controlplane_db.models

def test_startup_provisions_configured_marketplace_after_owner_schema(migration_database, monkeypatch):
    from controlplane_tenancy import marketplace, startup
    url = migration_database()
    schema_engine = create_engine(url)
    try:
        Base.metadata.create_all(schema_engine)
    finally:
        schema_engine.dispose()
    tenant = uuid.uuid4()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(marketplace, "MARKETPLACE_TENANT_ID", tenant)
    assert startup.main() == 0
    assert startup.main() == 0
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            row = connection.execute(text("SELECT name, is_active FROM tenants WHERE id = :id"), {"id": tenant}).one()
            assert row.is_active is True
            assert row.name == f"Marketplace {tenant}"
            connection.execute(text("UPDATE tenants SET name = 'Existing marketplace' WHERE id = :id"), {"id": tenant})
            marketplace.ensure_marketplace_tenant(connection)
            assert connection.execute(text("SELECT name FROM tenants WHERE id = :id"), {"id": tenant}).scalar_one() == "Existing marketplace"
            connection.execute(text("UPDATE tenants SET is_active = false WHERE id = :id"), {"id": tenant})
        with pytest.raises(RuntimeError, match="inactive"), engine.begin() as connection:
            marketplace.ensure_marketplace_tenant(connection)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT is_active FROM tenants WHERE id = :id"), {"id": tenant}).scalar_one() is False
    finally:
        engine.dispose()
