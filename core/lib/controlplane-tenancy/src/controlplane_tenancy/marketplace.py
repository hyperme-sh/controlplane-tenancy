"""One marketplace tenant setting shared by owner services."""

import os
import uuid

MARKETPLACE_TENANT_ID = uuid.UUID(
    (os.environ.get("MARKETPLACE_TENANT_ID") or "8f8e8d8c-7b6a-4a59-8c3d-2e1f0a9b8c7d")
)
