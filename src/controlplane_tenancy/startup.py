"""Provision the configured marketplace after the owning service provisions its schema."""

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from controlplane_db.session import default_database_url
from controlplane_tenancy.marketplace import ensure_marketplace_tenant


def main() -> int:
    engine = create_engine(
        make_url(default_database_url()).set(drivername="postgresql+psycopg")
    )
    try:
        with engine.begin() as connection:
            ensure_marketplace_tenant(connection)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
