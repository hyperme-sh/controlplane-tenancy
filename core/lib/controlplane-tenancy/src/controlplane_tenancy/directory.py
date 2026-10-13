"""Platform directory owner: detached views and caller-owned transactions.

Trusted server APIs. HTTP authorization, IdP proof and audit stay with callers;
these repositories filter tenant and validate tenant references before writes.
No method commits, rolls back or closes the supplied session.
"""
from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from controlplane_tenancy.tenant_membership import (
    create_tenant_membership_row,
)
from controlplane_db.models import (
    Group,
    Organization,
    OrganizationIdpLink,
    Role,
    User,
    UserGroupMembership,
    UserPreference,
)


class DirectoryLinkError(ValueError):
    """A referenced row is absent from the requested tenant."""


@dataclass(frozen=True)
class UserCreateData:
    email: str
    first_name: str
    last_name: str
    gender: str = "unspecified"
    is_active: bool = True


@dataclass(frozen=True)
class UserUpdateData:
    first_name: str | None = None
    last_name: str | None = None
    sociacl_attributes: dict | None = None


@dataclass(frozen=True)
class UserView:
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    email: str
    first_name: str
    last_name: str
    gender: str
    is_active: bool
    deleted_at: datetime | None
    role_id: uuid.UUID | None
    keycloak_sub: str | None
    _attributes: dict | None = field(repr=False)

    @property
    def sociacl_attributes(self) -> dict | None:
        return deepcopy(self._attributes)


@dataclass(frozen=True)
class RoleView:
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    name: str
    description: str | None
    _permissions: list = field(repr=False)

    @property
    def permissions(self) -> list:
        return deepcopy(self._permissions)


@dataclass(frozen=True)
class GroupView:
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    role_id: uuid.UUID


@dataclass(frozen=True)
class OrganizationView:
    id: uuid.UUID
    tenant_id: uuid.UUID
    legal_name: str


@dataclass(frozen=True)
class OrganizationIdpLinkView:
    id: uuid.UUID
    tenant_id: uuid.UUID
    organization_id: uuid.UUID
    provider: str
    external_key: str
    linked_by_sub: str


@dataclass(frozen=True)
class MembershipView:
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    group_id: uuid.UUID


def _view(row):
    if row is None:
        return None
    if isinstance(row, User):
        return UserView(row.id, row.tenant_id, row.email, row.first_name, row.last_name,
                        row.gender, row.is_active, row.deleted_at, row.role_id,
                        row.keycloak_sub, deepcopy(row.sociacl_attributes))
    if isinstance(row, Role):
        return RoleView(row.id, row.tenant_id, row.name, row.description, deepcopy(row.permissions))
    if isinstance(row, Group):
        return GroupView(row.id, row.tenant_id, row.name, row.description, row.role_id)
    if isinstance(row, Organization):
        return OrganizationView(row.id, row.tenant_id, row.legal_name)
    if isinstance(row, OrganizationIdpLink):
        return OrganizationIdpLinkView(row.id, row.tenant_id, row.organization_id,
                                       row.provider, row.external_key, row.linked_by_sub)
    if isinstance(row, UserGroupMembership):
        return MembershipView(row.id, row.tenant_id, row.user_id, row.group_id)
    raise TypeError("Unsupported directory row")


async def _require_reference(session, model, tenant_id, identity):
    present = await session.scalar(select(model.id).where(
        model.tenant_id == tenant_id, model.id == identity,
    ))
    if present is None:
        raise DirectoryLinkError("Reference must belong to the requested tenant")


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, tenant_id: uuid.UUID, body: UserCreateData) -> UserView:
        # Invite HTTP still gates this. Enrollment calls the same helper
        # as the service — it does not POST /api/v1/users as the renter.
        row = await create_tenant_membership_row(
            self._s,
            tenant_id,
            email=str(body.email).lower(),
            first_name=body.first_name,
            last_name=body.last_name,
            gender=body.gender,
            is_active=body.is_active,
        )
        return _view(row)

    async def list_active(self, tenant_id: uuid.UUID) -> list[UserView]:
        q = await self._s.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.deleted_at.is_(None),
            )
        )
        return [_view(row) for row in q.scalars().all()]

    async def list_active_paged(
        self,
        tenant_id: uuid.UUID,
        *,
        offset: int,
        limit: int,
        q: str | None,
    ) -> tuple[list[UserView], int]:
        cond = [
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
        ]
        if q and q.strip():
            term = f"%{q.strip()}%"
            cond.append(
                or_(
                    User.email.ilike(term),
                    User.first_name.ilike(term),
                    User.last_name.ilike(term),
                )
            )
        where_clause = and_(*cond)

        total_q = await self._s.execute(
            select(func.count()).select_from(User).where(where_clause)
        )
        total = int(total_q.scalar_one())

        rows_q = await self._s.execute(
            select(User)
            .where(where_clause)
            .order_by(User.email.asc())
            .offset(offset)
            .limit(limit)
        )
        return [_view(row) for row in rows_q.scalars().all()], total

    async def get(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> UserView | None:
        q = await self._s.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.id == user_id,
                User.deleted_at.is_(None),
            )
        )
        return _view(q.scalar_one_or_none())

    async def get_by_email(self, tenant_id: uuid.UUID, email: str) -> UserView | None:
        q = await self._s.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.email == email.lower(),
                User.deleted_at.is_(None),
            )
        )
        return _view(q.scalar_one_or_none())

    async def get_by_keycloak_sub(
        self, tenant_id: uuid.UUID, keycloak_sub: str
    ) -> UserView | None:
        q = await self._s.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.keycloak_sub == keycloak_sub,
                User.deleted_at.is_(None),
            )
        )
        return _view(q.scalar_one_or_none())

    async def get_any(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserView | None:
        """Include soft-deleted (for idempotent operations)."""
        q = await self._s.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == user_id)
        )
        return _view(q.scalar_one_or_none())

    async def _mutable_user(self, tenant_id, user_id):
        found = await self._s.execute(select(User).where(
            User.tenant_id == tenant_id, User.id == user_id,
            User.deleted_at.is_(None),
        ).with_for_update().execution_options(populate_existing=True))
        return found.scalar_one_or_none()

    async def update(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, body: UserUpdateData
    ) -> UserView | None:
        u = await self._mutable_user(tenant_id, user_id)
        if u is None:
            return None
        if body.first_name is not None:
            u.first_name = body.first_name
        if body.last_name is not None:
            u.last_name = body.last_name
        if body.sociacl_attributes is not None:
            u.sociacl_attributes = deepcopy(body.sociacl_attributes)
        await self._s.flush()
        await self._s.refresh(u)
        return _view(u)

    async def set_role(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID | None
    ) -> UserView | None:
        u = await self._mutable_user(tenant_id, user_id)
        if u is None:
            return None
        if role_id is not None:
            await _require_reference(self._s, Role, tenant_id, role_id)
        u.role_id = role_id
        await self._s.flush()
        await self._s.refresh(u)
        return _view(u)

    async def soft_delete(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        u = await self._mutable_user(tenant_id, user_id)
        if u is None:
            return False
        u.deleted_at = datetime.now(timezone.utc)
        u.is_active = False
        await self._s.flush()
        return True


class SqlRoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, tenant_id: uuid.UUID, role_id: uuid.UUID) -> RoleView | None:
        q = await self._s.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.id == role_id)
        )
        return _view(q.scalar_one_or_none())


class SqlGroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        tenant_id: uuid.UUID,
        name: str,
        description: str | None,
        role_id: uuid.UUID,
    ) -> GroupView:
        await _require_reference(self._s, Role, tenant_id, role_id)
        g = Group(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            description=description,
            role_id=role_id,
        )
        self._s.add(g)
        await self._s.flush()
        await self._s.refresh(g)
        return _view(g)

    async def get(self, tenant_id: uuid.UUID, group_id: uuid.UUID) -> GroupView | None:
        q = await self._s.execute(
            select(Group).where(Group.tenant_id == tenant_id, Group.id == group_id)
        )
        return _view(q.scalar_one_or_none())

    async def get_by_name(self, tenant_id: uuid.UUID, name: str) -> GroupView | None:
        result = await self._s.execute(select(Group).where(
            Group.tenant_id == tenant_id, Group.name == name,
        ))
        return _view(result.scalar_one_or_none())

    async def list_paged(
        self,
        tenant_id: uuid.UUID,
        *,
        offset: int,
        limit: int,
        q: str | None,
    ) -> tuple[list[GroupView], int]:
        cond = [Group.tenant_id == tenant_id]
        if q and q.strip():
            term = f"%{q.strip()}%"
            cond.append(
                or_(
                    Group.name.ilike(term),
                    Group.description.ilike(term),
                )
            )
        where_clause = and_(*cond)

        total_q = await self._s.execute(
            select(func.count()).select_from(Group).where(where_clause)
        )
        total = int(total_q.scalar_one())

        rows_q = await self._s.execute(
            select(Group)
            .where(where_clause)
            .order_by(Group.name.asc())
            .offset(offset)
            .limit(limit)
        )
        return [_view(row) for row in rows_q.scalars().all()], total


class SqlOrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, tenant_id: uuid.UUID, legal_name: str) -> OrganizationView:
        o = Organization(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            legal_name=legal_name,
        )
        self._s.add(o)
        await self._s.flush()
        await self._s.refresh(o)
        return _view(o)

    async def get(
        self, tenant_id: uuid.UUID, organization_id: uuid.UUID
    ) -> OrganizationView | None:
        q = await self._s.execute(
            select(Organization).where(
                Organization.tenant_id == tenant_id,
                Organization.id == organization_id,
            )
        )
        return _view(q.scalar_one_or_none())

    async def list_paged(
        self,
        tenant_id: uuid.UUID,
        *,
        offset: int,
        limit: int,
        q: str | None,
    ) -> tuple[list[OrganizationView], int]:
        cond = [Organization.tenant_id == tenant_id]
        if q and q.strip():
            term = f"%{q.strip()}%"
            cond.append(Organization.legal_name.ilike(term))
        where_clause = and_(*cond)

        total_q = await self._s.execute(
            select(func.count()).select_from(Organization).where(where_clause)
        )
        total = int(total_q.scalar_one())

        rows_q = await self._s.execute(
            select(Organization)
            .where(where_clause)
            .order_by(Organization.legal_name.asc())
            .offset(offset)
            .limit(limit)
        )
        return [_view(row) for row in rows_q.scalars().all()], total


class SqlOrganizationIdpLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_for_org(
        self, tenant_id: uuid.UUID, organization_id: uuid.UUID
    ) -> list[OrganizationIdpLinkView]:
        rows = await self._s.execute(
            select(OrganizationIdpLink)
            .where(
                OrganizationIdpLink.tenant_id == tenant_id,
                OrganizationIdpLink.organization_id == organization_id,
            )
            .order_by(OrganizationIdpLink.provider.asc(), OrganizationIdpLink.external_key.asc())
        )
        return [_view(row) for row in rows.scalars().all()]

    async def find(
        self, tenant_id: uuid.UUID, provider: str, external_key: str
    ) -> OrganizationIdpLinkView | None:
        row = await self._s.execute(
            select(OrganizationIdpLink).where(
                OrganizationIdpLink.tenant_id == tenant_id,
                OrganizationIdpLink.provider == provider,
                OrganizationIdpLink.external_key == external_key,
            )
        )
        return _view(row.scalar_one_or_none())

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        organization_id: uuid.UUID,
        provider: str,
        external_key: str,
        linked_by_sub: str,
    ) -> OrganizationIdpLinkView:
        await _require_reference(self._s, Organization, tenant_id, organization_id)
        link = OrganizationIdpLink(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            organization_id=organization_id,
            provider=provider,
            external_key=external_key,
            linked_by_sub=linked_by_sub,
        )
        self._s.add(link)
        await self._s.flush()
        await self._s.refresh(link)
        return _view(link)

    async def delete(
        self, tenant_id: uuid.UUID, organization_id: uuid.UUID, link_id: uuid.UUID
    ) -> bool:
        row = await self._s.execute(
            select(OrganizationIdpLink).where(
                OrganizationIdpLink.tenant_id == tenant_id,
                OrganizationIdpLink.organization_id == organization_id,
                OrganizationIdpLink.id == link_id,
            )
        )
        link = row.scalar_one_or_none()
        if link is None:
            return False
        await self._s.delete(link)
        await self._s.flush()
        return True


class SqlMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, group_id: uuid.UUID
    ) -> MembershipView:
        await _require_reference(self._s, User, tenant_id, user_id)
        await _require_reference(self._s, Group, tenant_id, group_id)
        m = UserGroupMembership(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            group_id=group_id,
        )
        self._s.add(m)
        await self._s.flush()
        await self._s.refresh(m)
        return _view(m)

    async def exists(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, group_id: uuid.UUID
    ) -> bool:
        q = await self._s.execute(
            select(UserGroupMembership.id)
            .join(User, User.id == UserGroupMembership.user_id)
            .join(Group, Group.id == UserGroupMembership.group_id)
            .where(
                UserGroupMembership.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
                Group.tenant_id == tenant_id,
                UserGroupMembership.user_id == user_id,
                UserGroupMembership.group_id == group_id,
            )
        )
        return q.scalar_one_or_none() is not None

    async def remove(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, group_id: uuid.UUID
    ) -> bool:
        q = await self._s.execute(
            select(UserGroupMembership).where(
                UserGroupMembership.tenant_id == tenant_id,
                UserGroupMembership.user_id == user_id,
                UserGroupMembership.group_id == group_id,
            )
        )
        row = q.scalar_one_or_none()
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True

    async def list_for_group(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID
    ) -> list[tuple[MembershipView, UserView]]:
        q = await self._s.execute(
            select(UserGroupMembership, User)
            .join(User, User.id == UserGroupMembership.user_id)
            .join(Group, Group.id == UserGroupMembership.group_id)
            .where(
                UserGroupMembership.tenant_id == tenant_id,
                UserGroupMembership.group_id == group_id,
                User.deleted_at.is_(None),
                User.tenant_id == tenant_id,
                Group.tenant_id == tenant_id,
            )
            .order_by(User.email.asc())
        )
        return [(_view(membership), _view(user)) for membership, user in q.all()]

    async def groups_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[GroupView]:
        q = await self._s.execute(
            select(Group)
            .join(UserGroupMembership, UserGroupMembership.group_id == Group.id)
            .join(User, User.id == UserGroupMembership.user_id)
            .where(
                UserGroupMembership.tenant_id == tenant_id,
                UserGroupMembership.user_id == user_id,
                Group.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
            )
            .order_by(Group.name.asc())
        )
        return [_view(row) for row in q.scalars().all()]


async def clear_model_preference(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Clear only model_name, in the caller's tenant-scoped transaction."""
    row = await session.scalar(select(UserPreference).where(
        UserPreference.tenant_id == tenant_id, UserPreference.user_id == user_id,
    ).with_for_update().execution_options(populate_existing=True))
    if row is not None and isinstance(row.preferences, dict):
        preferences = dict(row.preferences)
        preferences.pop("model_name", None)
        row.preferences = preferences
        await session.flush()
