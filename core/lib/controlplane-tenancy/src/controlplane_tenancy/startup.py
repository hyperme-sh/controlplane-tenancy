"""Apply schema heads, then provision the configured marketplace before apps seed."""

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from controlplane_db import startup as database_startup
from controlplane_db.session import default_database_url
from controlplane_tenancy.marketplace import ensure_marketplace_tenant


def main() -> int:
    database_startup.main()
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
