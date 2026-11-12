"""Offline statement and refusal tests; the session is explicitly mocked."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4, UUID
import pytest
from sqlalchemy.dialects import postgresql
from controlplane_tenancy.directory import DirectoryLinkError
from controlplane_tenancy.organization_membership import SqlOrganizationRoleRepository


def session():
    return SimpleNamespace(scalar=AsyncMock(side_effect=[uuid4(), uuid4()]), execute=AsyncMock(),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: ['admin', 'member', 'owner'])),
        commit=AsyncMock(), rollback=AsyncMock(), close=AsyncMock())


@pytest.mark.parametrize('roles', [None, '', [], ['owner','owner'], ['platform_admin'], ['owner',1], ['member']*4])
async def test_invalid_roles_refuse_before_reading_or_writing(roles):
    db = session()
    with pytest.raises(DirectoryLinkError): await SqlOrganizationRoleRepository(db).ensure(uuid4(), uuid4(), uuid4(), roles)
    db.scalar.assert_not_called(); db.execute.assert_not_called()


@pytest.mark.parametrize('value', [None, 'tenant', UUID(int=0)])
async def test_missing_scope_refuses_both_operations(value):
    db = session(); repo = SqlOrganizationRoleRepository(db)
    with pytest.raises(DirectoryLinkError): await repo.ensure(value, uuid4(), uuid4(), ['owner'])
    with pytest.raises(DirectoryLinkError): await repo.roles(uuid4(), value, uuid4())
    db.scalar.assert_not_called(); db.scalars.assert_not_called(); db.execute.assert_not_called()


@pytest.mark.parametrize('references', [[None], [uuid4(), None]])
async def test_missing_reference_never_grants(references):
    db = session(); db.scalar.side_effect = references
    with pytest.raises(DirectoryLinkError): await SqlOrganizationRoleRepository(db).ensure(uuid4(), uuid4(), uuid4(), ['owner'])
    db.execute.assert_not_called()


async def test_ensure_uses_scoped_locks_unique_insert_and_detached_roles():
    db = session(); tenant, org, user = uuid4(), uuid4(), uuid4()
    result = await SqlOrganizationRoleRepository(db).ensure(tenant, org, user, ['owner', 'admin'])
    assert result == ('admin', 'member', 'owner')
    statements = [call.args[0].compile(dialect=postgresql.dialect()) for call in db.scalar.call_args_list]
    assert all('FOR UPDATE' in str(statement) for statement in statements)
    assert tenant in statements[0].params.values() and org in statements[0].params.values()
    assert tenant in statements[1].params.values() and user in statements[1].params.values()
    assert 'users.is_active IS true' in str(statements[1]) and 'users.deleted_at IS NULL' in str(statements[1])
    statement = db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert 'ON CONFLICT ON CONSTRAINT uq_org_user_membership_role DO NOTHING' in str(statement)
    assert statement.params['role_m0'] == 'admin' and statement.params['role_m1'] == 'owner'
    read = db.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
    assert all(value in read.params.values() for value in (tenant, org, user))
    assert 'users.is_active IS true' in str(read) and 'users.deleted_at IS NULL' in str(read)
    db.commit.assert_not_called(); db.rollback.assert_not_called(); db.close.assert_not_called()


async def test_requested_roles_are_copied_before_awaiting_references():
    db = session(); requested = ['member']
    async def reference(_statement):
        requested[:] = ['owner']
        return uuid4()
    db.scalar.side_effect = reference
    await SqlOrganizationRoleRepository(db).ensure(uuid4(), uuid4(), uuid4(), requested)
    statement = db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert statement.params['role_m0'] == 'member'


async def test_database_driver_uuid_subclasses_are_valid_scope():
    class DriverUUID(UUID):
        pass
    db = session()
    scope = tuple(DriverUUID(str(uuid4())) for _ in range(3))
    assert await SqlOrganizationRoleRepository(db).ensure(*scope, ['member']) == ('admin', 'member', 'owner')
    db.execute.assert_awaited_once()
