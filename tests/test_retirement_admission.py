"""Caller-owned retirement transactions and cross-tenant admission fencing."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from controlplane_tenancy.tenant_membership import (
    create_tenant_membership_row, identity_retired_at, retire_identity,
)


async def test_retirement_is_immutable_and_prevents_recreation_in_every_tenant(async_engine,seed,monkeypatch):
    monkeypatch.setenv('ACCOUNT_CLOSURE_ENFORCEMENT_ENABLED','true')
    maker=async_sessionmaker(async_engine,expire_on_commit=False)
    subject=str(uuid.uuid4()); at=datetime.now(UTC)
    async with maker.begin() as session:
        assert await retire_identity(session,subject,at)==at
    async with maker.begin() as session:
        assert await retire_identity(session,subject,at+timedelta(days=1))==at
        assert await identity_retired_at(session,subject)==at
    for tenant in (seed.ta,seed.tb):
        async with maker.begin() as session:
            with pytest.raises(ValueError,match='retired'):
                await create_tenant_membership_row(session,tenant,email=uuid.uuid4().hex+'@example.invalid',first_name='Retired',last_name='Test',keycloak_sub=subject)


async def test_retirement_rolls_back_with_caller_transaction(async_engine):
    maker=async_sessionmaker(async_engine,expire_on_commit=False)
    subject=' exact-'+uuid.uuid4().hex+' '
    async with maker() as session:
        await retire_identity(session,subject,datetime.now(UTC))
        assert await identity_retired_at(session,subject) is not None
        await session.rollback()
    async with maker() as session:
        assert await identity_retired_at(session,subject) is None
