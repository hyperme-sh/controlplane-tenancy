"""Organization-scoped roles, using caller-owned transactions and authorization."""
from __future__ import annotations

from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from controlplane_db.models import Organization, OrganizationUserMembership, User
from controlplane_tenancy.directory import DirectoryLinkError


def _scope(tenant_id: UUID, organization_id: UUID, user_id: UUID) -> None:
    if any(not isinstance(value, UUID) or not value.int for value in (tenant_id, organization_id, user_id)):
        raise DirectoryLinkError('Explicit organization membership scope required')


class SqlOrganizationRoleRepository:
    """Trusted service adapter; neither a session validator nor an admin grant.

    Callers set the tenant GUC and authenticate authority before using this API.
    No method commits, rolls back, closes, creates users or alters tenant roles.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def roles(self, tenant_id: UUID, organization_id: UUID, user_id: UUID) -> tuple[str, ...]:
        _scope(tenant_id, organization_id, user_id)
        rows = await self._s.scalars(select(OrganizationUserMembership.role).join(
            User, (User.id == OrganizationUserMembership.user_id) & (User.tenant_id == OrganizationUserMembership.tenant_id)
        ).where(OrganizationUserMembership.tenant_id == tenant_id,
                OrganizationUserMembership.organization_id == organization_id,
                OrganizationUserMembership.user_id == user_id,
                User.is_active.is_(True), User.deleted_at.is_(None))
            .order_by(OrganizationUserMembership.role))
        return tuple(rows.all())

    async def ensure(self, tenant_id: UUID, organization_id: UUID, user_id: UUID,
                     roles: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        """Add only explicitly authorized roles; an identical retry adds no rows.

        Preserve unrelated roles. Existing organization and active tenant user
        rows are locked before writing. The owner transaction spans the grant.
        """
        _scope(tenant_id, organization_id, user_id)
        if type(roles) not in (tuple, list) or not 1 <= len(roles) <= 3:
            raise DirectoryLinkError('Explicit organization roles required')
        requested = tuple(roles)
        if any(type(role) is not str or role not in ('member', 'owner', 'admin') for role in requested) or len(set(requested)) != len(requested):
            raise DirectoryLinkError('Explicit organization roles required')
        organization = await self._s.scalar(select(Organization.id).where(
            Organization.tenant_id == tenant_id, Organization.id == organization_id).with_for_update())
        if organization is None:
            raise DirectoryLinkError('Organization membership reference unavailable')
        user = await self._s.scalar(select(User.id).where(User.tenant_id == tenant_id, User.id == user_id,
            User.is_active.is_(True), User.deleted_at.is_(None)).with_for_update())
        if user is None:
            raise DirectoryLinkError('Organization membership reference unavailable')
        await self._s.execute(insert(OrganizationUserMembership).values([
            dict(id=uuid4(), tenant_id=tenant_id, organization_id=organization_id, user_id=user_id, role=role)
            for role in sorted(requested)
        ]).on_conflict_do_nothing(constraint='uq_org_user_membership_role'))
        return await self.roles(tenant_id, organization_id, user_id)
