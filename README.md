# controlplane-tenancy

Shared database-session context, PostgreSQL tenant GUC, membership helpers,
marketplace tenant configuration, detached directory views and tenant registry
queries. Depends on `controlplane-db`, not legacy API or product implementations.

`MARKETPLACE_TENANT_ID` is read at import: unset/empty uses the default marketplace
identity, invalid UUIDs fail startup. Configure the same value across consumers.
`python -m controlplane_tenancy.startup` applies database startup migrations then
provisions the marketplace tenant. Run it only under deployment-owner authority.
An existing active marketplace tenant is preserved; an inactive one fails startup.

Directory repositories filter tenant IDs and validate tenant-bound references.
Callers retain HTTP authorization, IdP proof, audit and commit/rollback ownership.
Views are detached and frozen, with copy-isolated JSON attributes. Updates lock
and refresh rows; registry queries preserve the caller's database authority.

## Development

Use Python 3.13 and uv 0.11.26 with read access to the private database dependency:

```sh
bash scripts/check-package.sh
```

The distribution metadata pins controlplane-db to coordinated migration commit
`17e8c60bc2fea5af890299624ec97e1e7148b2a2`. Tests run from source, an ordinary
fresh-wheel install that resolves that dependency, and a rebuilt source archive.
Wheel contents are compared against the current runtime source.

Set `TEST_DATABASE_URL` to a disposable PostgreSQL admin database to run directory
integration cases; the fixture creates and drops a unique database and applies
platform migrations there. Without it, those cases are skipped. Do not point the
test fixture at a shared or deployed server. Legacy aliases and consuming-service
HTTP/auth behavior require separate integration validation.

## Automated checks

The included main-branch/manual workflow uses disposable hosted workers and a
PostgreSQL service. It requires `DEPENDENCY_READ_TOKEN` scoped to contents:read
on hyperme-sh/controlplane-db. It is supplied only to the dependency-install/test
step via an exact-repository Git HTTP header. Fork and pull-request workflows do
not receive this credential. No token is committed or copied from a deployment.
Repository Actions remain disabled until dependency access and workflow policy
are configured and a destination run passes; local checks are not CI acceptance.
