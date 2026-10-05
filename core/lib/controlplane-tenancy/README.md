# controlplane-tenancy

Shared database-session context, Postgres tenant GUC, membership helpers and the
marketplace tenant setting. Public modules are declared in the ownership and
import manifests. This package depends on `controlplane-db`, not legacy `api`
or product implementations.

`MARKETPLACE_TENANT_ID` is read once at process import. An unset or empty value
uses the existing marketplace identity; an invalid UUID fails startup. Set the
same environment value across services. Both compose files propagate it through
the common application environment. `AIUDITOR_CRAWL_TENANT_ID` and
`HYPERMESH_TENANT_IDS` retain their explicit service-specific override behavior.

Legacy persistence modules alias the shared implementations, so old and new
imports use the same ContextVar and session maker. Public source contracts use
the workspace's 0.10.0 train. No schema or migration change accompanies extraction.

`python -m controlplane_tenancy.startup` runs the database migration command and
then provisions the configured marketplace before applications seed tenant data.
An existing active tenant is preserved; an inactive tenant fails startup. Both
Compose migration jobs and the Edge/Hypermesh entrypoints use this command.
Frozen migrations are unchanged. Browser enrollment reads the deployed target
from `GET /auth/enrollment/marketplace` instead of embedding a tenant UUID.
