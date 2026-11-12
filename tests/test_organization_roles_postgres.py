"""Organization role owner checks on CI-owned disposable PostgreSQL only."""
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker
from controlplane_db.models import OrganizationUserMembership, User, UserGroupMembership
from controlplane_tenancy.directory import DirectoryLinkError, SqlOrganizationRepository, SqlUserRepository, UserCreateData
from controlplane_tenancy.organization_membership import SqlOrganizationRoleRepository


@pytest.fixture
async def people(async_engine, seed):
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as session:
        users, orgs = SqlUserRepository(session), SqlOrganizationRepository(session)
        user = await users.create(seed.ta, UserCreateData('member-'+uuid4().hex+'@example.invalid', 'Member', 'One'))
        other = await users.create(seed.tb, UserCreateData('other-'+uuid4().hex+'@example.invalid', 'Member', 'Two'))
        org = await orgs.create(seed.ta, 'Organization '+uuid4().hex)
        sibling = await orgs.create(seed.ta, 'Sibling '+uuid4().hex)
        foreign = await orgs.create(seed.tb, 'Foreign '+uuid4().hex)
        await session.commit()
    return maker, seed.ta, seed.tb, user.id, other.id, org.id, sibling.id, foreign.id


async def test_explicit_roles_replay_and_no_tenant_or_group_promotion(people):
    maker, tenant, _, user, _, org, sibling, _ = people
    async with maker() as session:
        repo = SqlOrganizationRoleRepository(session)
        original_role = await session.scalar(select(User.role_id).where(User.id == user))
        assert await repo.ensure(tenant, org, user, ['member']) == ('member',)
        assert await repo.ensure(tenant, org, user, ['owner', 'admin']) == ('admin', 'member', 'owner')
        assert await repo.ensure(tenant, org, user, ['owner', 'admin']) == ('admin', 'member', 'owner')
        assert await repo.roles(tenant, sibling, user) == ()
        assert await session.scalar(select(func.count()).select_from(OrganizationUserMembership)) == 3
        assert await session.scalar(select(User.role_id).where(User.id == user)) == original_role
        assert await session.scalar(select(func.count()).select_from(UserGroupMembership)) == 0
        await session.commit()
    async with maker() as session:
        assert await SqlOrganizationRoleRepository(session).roles(tenant, org, user) == ('admin', 'member', 'owner')


async def test_cross_tenant_or_absent_references_cannot_gain_roles(people):
    maker, tenant, other_tenant, user, other_user, org, _, foreign_org = people
    async with maker() as session:
        repo = SqlOrganizationRoleRepository(session)
        for scope in [(other_tenant, org, user), (tenant, foreign_org, user), (tenant, org, other_user), (tenant, uuid4(), user)]:
            with pytest.raises(DirectoryLinkError): await repo.ensure(*scope, ['owner'])
            assert await repo.roles(*scope) == ()
        assert await session.scalar(select(func.count()).select_from(OrganizationUserMembership)) == 0


async def test_caller_rollback_removes_partial_reconciliation(people):
    maker, tenant, _, user, _, org, _, _ = people
    async with maker() as session:
        with pytest.raises(DirectoryLinkError):
            async with session.begin():
                repo = SqlOrganizationRoleRepository(session)
                await repo.ensure(tenant, org, user, ['owner'])
                await repo.ensure(tenant, uuid4(), user, ['owner'])
    async with maker() as session:
        assert await SqlOrganizationRoleRepository(session).roles(tenant, org, user) == ()


async def test_concurrent_replay_preserves_one_set_of_roles(people):
    maker, tenant, _, user, _, org, _, _ = people
    async def grant():
        async with maker() as session, session.begin():
            return await SqlOrganizationRoleRepository(session).ensure(tenant, org, user, ['owner', 'admin'])
    assert await asyncio.gather(grant(), grant()) == [('admin', 'owner'), ('admin', 'owner')]
    async with maker() as session:
        assert await session.scalar(select(func.count()).select_from(OrganizationUserMembership)) == 2


@pytest.mark.parametrize('closed', [False, True])
async def test_inactive_or_deleted_users_cannot_read_or_gain_roles(people, closed):
    maker, tenant, _, user, _, org, _, _ = people
    async with maker() as session:
        repo = SqlOrganizationRoleRepository(session)
        await repo.ensure(tenant, org, user, ['member'])
        row = await session.get(User, user)
        if closed: row.deleted_at = datetime.now(timezone.utc)
        else: row.is_active = False
        await session.flush()
        assert await repo.roles(tenant, org, user) == ()
        with pytest.raises(DirectoryLinkError): await repo.ensure(tenant, org, user, ['admin'])
