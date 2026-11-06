# controlplane-tenancy

`controlplane-tenancy` is the shared Python library for tenant context in the
Hypermesh control plane. It sets the PostgreSQL tenant session variable, writes
and reads membership rows, and provisions the marketplace tenant. Directory and
registry calls sit on the same session the caller already opened. The package
version is **0.14.0**. It requires Python 3.13 and depends on
[`controlplane-db`](https://github.com/hyperme-sh/controlplane-db) 0.1.0 at
commit `95ef61433374274f4a4fc287e15982be6357e1cc` and `sqlalchemy>=2.0.43`.

## Why

Hosts, renters, and operators all show up as tenants in one PostgreSQL database.
Every control-plane service that touches those rows has to apply the same
session tenant, the same membership identity, and the same marketplace tenant
id. Putting that in each service lets the filters and the marketplace row
drift. This library is the shared contract. Calling services keep HTTP
authorization, identity-provider proof, audit logging, and commit or rollback.

## How it works

Import the submodules directly. `controlplane_tenancy` does not re-export them.

| Module | Role |
| --- | --- |
| `db_session` | Holds the request `AsyncSession` in a context variable. |
| `tenant_guc` | Sets `app.current_tenant_id` for row-level security on that session. |
| `tenant_membership` | Inserts and looks up `users` memberships, role grants, and identity retirement. |
| `marketplace`, `startup` | Reads `MARKETPLACE_TENANT_ID` and provisions that tenant after migrations. |
| `directory` | Tenant-filtered repositories that return detached, frozen views. |
| `tenant_registry` | Pages tenant ids and reads the active flag on the caller's session. |
| `account_profile` | Disables a retired subject's memberships and erases personal profile data in one scope. |

`set_current_tenant_id_guc` runs `set_config('app.current_tenant_id', ..., true)`,
so the value lasts for the current transaction. An id string selects that
tenant. `None` stores an empty string, which is platform scope for policies
that allow `tenant_id IS NULL`.

A membership is a `users` row with `tenant_id` set. Later lookups match email
or `keycloak_sub`. Subjects are stored as given; the helpers do not trim a
subject into a different identity. When
`ACCOUNT_CLOSURE_ENFORCEMENT_ENABLED=true`, creating a membership checks the
canonical retirement row first and refuses a retired subject in every tenant.
`retire_identity` records the first retirement time and leaves that timestamp
in place. `lock_identity` takes a transaction-scoped advisory lock so retirement
and membership creation serialize. The caller commits.

Directory repositories filter by the tenant id argument and reject links to a
user, role, group, or organization outside that tenant (`DirectoryLinkError`).
Views are frozen dataclasses. JSON attributes (`sociacl_attributes`, role
permissions) are copied on the way out and on the way back in. Updates lock
the row, flush, and refresh. No repository method commits, rolls back, or
closes the session.

`account_profile.disable_subject_memberships` and `purge_retired_profile`
require the session GUC to match the tenant argument (`None` is platform
scope). Personal-profile erasure waits 89 days
(`ACCOUNT_PROFILE_RETENTION`), unless `ACCOUNT_CLOSURE_RETENTION=none`. Those
helpers clear personal profile fields, preferences, and sign-in material in
the requested scope. Billing and payment rows stay.

Registry reads use the caller's existing database role. `tenant_ids_page`
returns an id-ordered page (limit 1 through 1000, default 100). `tenant_active`
can hold `FOR UPDATE` until the caller finishes the transaction.

## Practical use

### Install

The library is not published on PyPI. Install it from Git with Python 3.13.
`controlplane-db` brings `asyncpg` 0.32.0, `psycopg` 3.3.6, and Alembic. The
lockfile in this repository resolves SQLAlchemy 2.1.6.

```sh
uv venv --python 3.13
uv pip install "controlplane-tenancy @ git+https://github.com/hyperme-sh/controlplane-tenancy.git"
```

In another project's `pyproject.toml`:

```toml
dependencies = [
  "controlplane-tenancy @ git+https://github.com/hyperme-sh/controlplane-tenancy.git",
]
```

That URL tracks the default branch, whose package version is 0.14.0. The
prerelease tag `0.24.0-test.0` is the same tree. The GitHub release `v0.24.0`
is an earlier commit whose package version is 0.24.0 and whose
`controlplane-db` pin is `6ee52fe3e775548956cada649715fdde80f6cd1d`. Use the
default branch or `0.24.0-test.0` to match this document. Channel details are
in [docs/releasing.md](docs/releasing.md).

### Tenant context

Configure one session maker at process start. On each request, bind the
session, then set the GUC before any repository call. Aligning the JWT tenant
claim with the `X-Tenant-ID` header stays in the calling service; the GUC still
has to be set on the session those repositories use.

```python
import os
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from controlplane_tenancy import db_session
from controlplane_tenancy.tenant_guc import set_current_tenant_id_guc

engine = create_async_engine(os.environ["DATABASE_URL"])
db_session.configure_session_maker(async_sessionmaker(engine, expire_on_commit=False))


async def in_tenant(session: AsyncSession, tenant_id: uuid.UUID | None):
    token = db_session.set_db_session(session)
    try:
        await set_current_tenant_id_guc(session, tenant_id)
        current = db_session.get_db_session()
        # directory, membership, and registry calls use `current`
        await current.commit()
    finally:
        db_session.reset_db_session(token)
```

`DATABASE_URL` defaults, via `controlplane-db`, to
`postgresql+asyncpg://controlplane_app:controlplane_app@localhost:5432/controlplane`.

### Membership helpers

```python
from controlplane_tenancy.marketplace import MARKETPLACE_TENANT_ID
from controlplane_tenancy.tenant_membership import (
    create_tenant_membership_row,
    get_active_tenant_role_member,
    get_tenant_membership_row,
)

existing = await get_tenant_membership_row(
    session,
    MARKETPLACE_TENANT_ID,
    email="ada@example.com",
    keycloak_sub=subject,
)
if existing is None:
    await create_tenant_membership_row(
        session,
        MARKETPLACE_TENANT_ID,
        email="ada@example.com",
        first_name="Ada",
        last_name="Lovelace",
        keycloak_sub=subject,
    )

admin = await get_active_tenant_role_member(
    session,
    MARKETPLACE_TENANT_ID,
    keycloak_sub=subject,
    role="admin",
)
await session.commit()
```

`get_tenant_membership_row` tries the normalized email, then the Keycloak
subject, and ignores soft-deleted rows. `get_active_tenant_role_member` returns
the user when the tenant is active and the subject holds that role on the user
row or through a group of the same name in that tenant. Email is not a role
key. `get_tenant_role_group_ids` returns the tenant-scoped group ids for a
role name.

`SqlUserRepository.create` in `controlplane_tenancy.directory` calls
`create_tenant_membership_row` and returns a detached `UserView`. The user
service invite route, `POST /api/v1/users`, remains the HTTP door and still
requires `can_invite_members`, a name, and a tenant claim on the JWT.

### Marketplace tenant configuration

`MARKETPLACE_TENANT_ID` is read once, at import. Unset or empty uses
`8f8e8d8c-7b6a-4a59-8c3d-2e1f0a9b8c7d`. Any other value must be a UUID; an
invalid value raises while the module is importing. Set the same value on
every process that enrolls members or provisions the database.

```sh
export DATABASE_URL=postgresql+asyncpg://controlplane_app:controlplane_app@localhost:5432/controlplane
export MARKETPLACE_TENANT_ID=8f8e8d8c-7b6a-4a59-8c3d-2e1f0a9b8c7d
export CONTROLPLANE_MIGRATION_MODE=owners
# Set only when the database has no schema yet.
export CONTROLPLANE_DB_BOOTSTRAP=1
python -m controlplane_tenancy.startup
```

`CONTROLPLANE_MIGRATION_MODE=owners` selects the packaged migration chains
Hypermesh deployments apply. The default, `legacy`, applies the frozen mixed
chain instead. Startup applies those migrations, then inserts the marketplace
tenant when the id is absent (`name` is `Marketplace <uuid>`, `is_active`
true). A second run leaves an existing active row and its name unchanged. An
inactive row raises `RuntimeError: Configured marketplace tenant is inactive`
and stays inactive. `CONTROLPLANE_DB_BOOTSTRAP=1` permits creating schema on
an empty database; leave it unset when a schema is already present.

To provision inside an existing transaction after migrations have already run:

```python
from sqlalchemy import create_engine

from controlplane_tenancy.marketplace import ensure_marketplace_tenant

engine = create_engine(
    "postgresql+psycopg://controlplane_app:controlplane_app@localhost:5432/controlplane"
)
with engine.begin() as connection:
    ensure_marketplace_tenant(connection)
```

Migration mode details live in the
[controlplane-db README](https://github.com/hyperme-sh/controlplane-db/blob/main/README.md).

## How Hypermesh uses it

Lease, host, and renter rows in the control plane are tenant-scoped. The
service handling an authenticated request aligns the caller's tenant with
`X-Tenant-ID`, then calls `set_current_tenant_id_guc` on that request's
session before it reads or writes. PostgreSQL row-level security then limits
the statement to that host or renter. Platform work that is allowed to see
rows with a null tenant id passes `None`.

The marketplace is one shared tenant, not a tenant per listing. Renter
enrollment and host membership insert a `users` row for `MARKETPLACE_TENANT_ID`
through `create_tenant_membership_row`. A renter token does not create that row
by calling `POST /api/v1/users` or `POST /api/v1/tenants/`. Deployments run
`python -m controlplane_tenancy.startup` before application seed so every
consumer attaches members to the same active marketplace row.

Directory repositories back control-plane user, role, group, organization, and
identity-provider link traffic. Operator inventory pages tenants with
`tenant_ids_page` and checks `tenant_active` without switching database role.
Retirement traffic uses `retire_identity` and `account_profile` in the caller's
transaction so a rolled-back request does not leave a partial closure.

## Develop and test

CI uses Python 3.13 and uv 0.11.26.

```sh
git clone https://github.com/hyperme-sh/controlplane-tenancy.git
cd controlplane-tenancy
bash scripts/check-package.sh
```

The script checks `uv.lock`, runs the test suite from the source tree, builds
a wheel, installs that wheel into a clean environment, and rebuilds the wheel
from the sdist. The three runs must agree.

Directory, marketplace startup, retirement, and profile tests need a disposable
PostgreSQL 17 server. The fixture creates and drops a unique database per case
and applies the platform migrations from the installed `controlplane-db`.
Point `TEST_DATABASE_URL` at an admin database you can afford to lose. A test
that requests the fixture fails if the variable is unset.

```sh
export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres
bash scripts/check-package.sh
```

`bash scripts/check-package.sh --fixtures` installs the wheels in
`tests_artifacts/dependencies` instead of resolving the `controlplane-db` Git
pin. Those wheels are checked against the lock and are left out of the
published sdist and wheel. Pull-request CI uses this mode with a disposable
PostgreSQL service. Main CI resolves the Git pin and runs the same package
script.

## Release and versioning

This tree's Python package version is **0.14.0**. Successful validation of
`main` can publish an immutable prerelease named `0.24.0-test.N`. That name is
the coordinated test train; the wheel inside it is still 0.14.0. The GitHub
release `v0.24.0` is an earlier package. Tags, channels, and the publisher
are documented in [docs/releasing.md](docs/releasing.md).

## License

This package is licensed under [Apache-2.0](LICENSE). Dependencies retain their
own licenses; this declaration does not relicense bundled third-party material.
