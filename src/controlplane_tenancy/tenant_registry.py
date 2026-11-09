"""Platform tenant registry reads using caller-owned sessions and locks."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from controlplane_db.models import Tenant


def tenant_ids_sync(session: Session) -> list[UUID]:
    """Enumerate the registry under the caller's existing database authority."""
    return list(session.execute(select(Tenant.id)).scalars().all())


async def tenant_ids_page(session: AsyncSession, *, after: UUID | None = None,
                          limit: int = 100) -> list[UUID]:
    """Return an ordered bounded registry page without changing session authority."""
    if not 1 <= limit <= 1000:
        raise ValueError("Tenant page limit must be between 1 and 1000")
    stmt = select(Tenant.id).order_by(Tenant.id).limit(limit)
    if after is not None:
        stmt = stmt.where(Tenant.id > after)
    return list((await session.scalars(stmt)).all())


async def tenant_active(session: AsyncSession, tenant_id: UUID, *,
                        lock: bool = False) -> bool | None:
    """Read active status, optionally holding its row lock until caller completion."""
    stmt = select(Tenant.is_active).where(Tenant.id == tenant_id)
    if lock:
        # FOR SHARE fences tenant changes while allowing foreign-key checks.
        stmt = stmt.with_for_update(read=True)
    return await session.scalar(stmt)
