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
the workspace's shared source-contract train (currently 0.18.0). No schema or migration change accompanies extraction.

`python -m controlplane_tenancy.startup` runs the database migration command and
then provisions the configured marketplace before applications seed tenant data.
An existing active tenant is preserved; an inactive tenant fails startup. Both
Compose migration jobs and the Edge/Hypermesh entrypoints use this command.
Frozen migrations are unchanged. Browser enrollment reads the deployed target
from `GET /auth/enrollment/marketplace` instead of embedding a tenant UUID.

`get_tenant_role_group_ids` returns tenant-scoped opaque group IDs for a user/role.
Product policies consume these IDs without querying platform membership tables.

## Platform directory owner contract

`controlplane_tenancy.directory` owns tenant-bound users, roles, organizations,
IdP links, groups, memberships and model-preference clearing. Services keep
HTTP authorization, provider proof, audit and transaction commit/rollback.
Every repository read filters tenant; writes validate tenant references and
never commit or close the supplied session. User updates and preference clearing
lock and refresh the relevant row before mutation.

The owner returns frozen detached views, with copy-isolated JSON attributes and
permissions, rather than ORM entities. API body adaptation remains in user-service.
Membership joins filter both sides' tenant; mismatched historical rows cannot
supply another tenant's user or group. Hypermesh host registration reuses the
existing `get_tenant_role_group_ids` owner helper for opaque host-group IDs.
Existing host identity checks, tenant-state checks and transaction locks remain.

The contract intentionally advances the six source-contract versions to 0.18.0;
control-plane 0.8.0, event/service versions and hm1/v=1 are unchanged. No schema,
provider operation, new HTTP endpoint or deployment is added.

`controlplane_tenancy.tenant_registry` owns tenant enumeration and status reads, preserving caller database authority, transactions and optional tenant row locks.
