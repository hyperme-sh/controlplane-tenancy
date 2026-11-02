"""One marketplace tenant setting shared by owner services."""

import os
import uuid

from sqlalchemy.engine import Connection

MARKETPLACE_TENANT_ID = uuid.UUID(
    (os.environ.get("MARKETPLACE_TENANT_ID") or "8f8e8d8c-7b6a-4a59-8c3d-2e1f0a9b8c7d")
)


def ensure_marketplace_tenant(connection: Connection) -> None:
    """Create the configured tenant or adopt its existing active row unchanged."""
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert
    from controlplane_db.models import Tenant

    connection.execute(
        insert(Tenant)
        .values(
            id=MARKETPLACE_TENANT_ID,
            name=f"Marketplace {MARKETPLACE_TENANT_ID}",
            is_active=True,
        )
        .on_conflict_do_nothing(index_elements=[Tenant.id])
    )
    active = connection.execute(
        select(Tenant.is_active).where(Tenant.id == MARKETPLACE_TENANT_ID)
    ).scalar_one()
    if not active:
        raise RuntimeError("Configured marketplace tenant is inactive")
