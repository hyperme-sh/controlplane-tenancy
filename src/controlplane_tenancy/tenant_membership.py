"""Internal tenant-membership writer.

A membership is a ``users`` row with ``tenant_id`` set, matched later by
email or ``keycloak_sub``. This is the same insert the invite repository
uses. It is a service/repository call with an explicit tenant id.

Not a public self-join. Not ``POST /api/v1/users`` (that HTTP door still
requires ``can_invite_members``, names, and a tenant claim on the JWT).
A raw OIDC renter cannot call that route. Not ``POST /api/v1/tenants/``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from controlplane_db.models import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from controlplane_tenancy.marketplace import (
    MARKETPLACE_TENANT_ID,  # noqa: F401 - legacy public export
)

# Existing Hypermesh marketplace tenant. Enrollment INSERTs the users row
# here. Do not assume the row exists (seeded renter has none today).


async def get_tenant_membership_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    email: str | None = None,
    keycloak_sub: str | None = None,
) -> User | None:
    if email:
        found = await session.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                func.lower(User.email) == email.strip().lower(),
                User.deleted_at.is_(None),
            )
        )
        row = found.scalar_one_or_none()
        if row is not None:
            return row
    if keycloak_sub:
        found = await session.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.keycloak_sub == keycloak_sub,
                User.deleted_at.is_(None),
            )
        )
        return found.scalar_one_or_none()
    return None


async def _keycloak_sub_is_free(
    session: AsyncSession, tenant_id: uuid.UUID, keycloak_sub: str
) -> bool:
    found = await session.execute(
        select(User.id).where(
            User.tenant_id == tenant_id, User.keycloak_sub == keycloak_sub
        )
    )
    return found.scalar_one_or_none() is None


async def create_tenant_membership_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    email: str,
    first_name: str,
    last_name: str,
    gender: str = "unspecified",
    is_active: bool = True,
    keycloak_sub: str | None = None,
) -> User:
    """INSERT a membership row. Caller is the service, not a renter JWT.

    Never assume a ``public.users`` row already exists for the identified
    Keycloak person. Match later by email or ``keycloak_sub``.
    """
    # Subjects are opaque. Never trim them into another identity.
    sub = keycloak_sub if keycloak_sub and keycloak_sub.strip() else None
    if (
        sub is not None
        and os.environ.get("ACCOUNT_CLOSURE_ENFORCEMENT_ENABLED", "").lower() == "true"
    ):
        from controlplane_db.models import IdentityRetirement

        await lock_identity(session, sub)
        if await session.get(IdentityRetirement, sub) is not None:
            raise ValueError("Identity has been retired")
    if sub is not None and not await _keycloak_sub_is_free(session, tenant_id, sub):
        sub = None
    row = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=str(email).strip().lower(),
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        is_active=is_active,
        activated_at=datetime.now(UTC) if is_active else None,
        keycloak_sub=sub,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get_active_tenant_role_member(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    keycloak_sub: str,
    role: str,
) -> User | None:
    """Recheck active tenant, subject binding and direct or grouped role assignment.

    Email is deliberately absent: a role grant belongs to a bound subject, not
    to another account that happens to present the same email claim.
    """
    from controlplane_db.models import Group, Role, Tenant, UserGroupMembership
    from sqlalchemy import or_

    direct = await session.scalar(
        select(User)
        .join(Tenant, Tenant.id == User.tenant_id)
        .join(Role, Role.id == User.role_id)
        .where(
            User.tenant_id == tenant_id,
            User.keycloak_sub == keycloak_sub,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
            Tenant.is_active.is_(True),
            or_(Role.tenant_id == tenant_id, Role.tenant_id.is_(None)),
            func.lower(Role.name) == role.lower(),
        )
        .limit(1)
    )
    if direct is not None:
        return direct

    result = await session.execute(
        select(User)
        .join(Tenant, Tenant.id == User.tenant_id)
        .join(
            UserGroupMembership,
            (UserGroupMembership.user_id == User.id)
            & (UserGroupMembership.tenant_id == User.tenant_id),
        )
        .join(
            Group,
            (Group.id == UserGroupMembership.group_id)
            & (Group.tenant_id == User.tenant_id),
        )
        .where(
            User.tenant_id == tenant_id,
            User.keycloak_sub == keycloak_sub,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
            Tenant.is_active.is_(True),
            func.lower(Group.name) == role.lower(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_tenant_role_group_ids(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    role: str,
) -> list[uuid.UUID]:
    """Return only tenant-scoped durable groups authorizing this role.

    Products apply their own group policies to opaque IDs; membership tables
    remain owned and queried by this shared contract.
    """
    from controlplane_db.models import Group, User, UserGroupMembership

    return list(
        await session.scalars(
            select(UserGroupMembership.group_id)
            .join(Group, Group.id == UserGroupMembership.group_id)
            .join(User, User.id == UserGroupMembership.user_id)
            .where(
                UserGroupMembership.tenant_id == tenant_id,
                UserGroupMembership.user_id == user_id,
                Group.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
                func.lower(Group.name) == role.lower(),
            )
        )
    )


async def lock_identity(session: AsyncSession, subject: str) -> None:
    """Serialize membership creation against realm-wide retirement; caller commits."""
    from sqlalchemy import text

    if not subject or not subject.strip() or len(subject) > 512:
        raise ValueError("An exact identity subject is required")
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"identity-retirement:{subject}"},
    )


async def retire_identity(
    session: AsyncSession, subject: str, retired_at: datetime
) -> datetime:
    """Permanently fence new memberships; return immutable first retirement time."""
    from controlplane_db.models import IdentityRetirement
    from sqlalchemy.dialects.postgresql import insert

    if retired_at.tzinfo is None or retired_at.utcoffset() is None:
        raise ValueError("An aware retirement time is required")
    await lock_identity(session, subject)
    await session.execute(
        insert(IdentityRetirement)
        .values(
            subject=subject,
            retired_at=retired_at,
        )
        .on_conflict_do_nothing(index_elements=["subject"])
    )
    return (await session.get(IdentityRetirement, subject)).retired_at


async def identity_retired_at(session: AsyncSession, subject: str) -> datetime | None:
    """Read the exact committed retirement marker without exposing its table."""
    from controlplane_db.models import IdentityRetirement

    if not subject or not subject.strip() or len(subject) > 512:
        raise ValueError("An exact identity subject is required")
    row = await session.get(IdentityRetirement, subject, populate_existing=True)
    return row.retired_at if row is not None else None
