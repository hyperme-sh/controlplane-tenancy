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
`6ee52fe3e775548956cada649715fdde80f6cd1d`. Tests run from source, an ordinary
fresh-wheel install that resolves that dependency, and a rebuilt source archive.
Wheel contents are compared against the current runtime source.

Set `TEST_DATABASE_URL` to a disposable PostgreSQL admin database to run directory
integration cases; the fixture creates and drops a unique database and applies
platform migrations there. Without it, those cases are skipped. Do not point the
test fixture at a shared or deployed server. Legacy aliases and consuming-service
HTTP/auth behavior require separate integration validation.

## Automated checks

The included main-branch/manual workflow uses the shared-local self-hosted Linux runners and a
PostgreSQL service. It requires `DEPENDENCY_READ_TOKEN` scoped to contents:read
on hyperme-sh/controlplane-db. It is supplied only to the dependency-install/test
step via an exact-repository Git HTTP header. Fork and pull-request workflows do
not receive this credential. No token is committed or copied from a deployment.
The main lane retains scoped dependency access; local checks are not CI acceptance.

## Release channels

Main validation retains its exact qualified files in Actions artifacts. It does
not create GitHub releases or tags. Historical `test-<commit>` prereleases remain
qualification evidence and do not establish an accepted stable release.

Stable publication requires an explicit `vMAJOR.MINOR.PATCH` tag, the exact
successful main validation artifact, compatible declared contracts and an actual
immutable stable baseline. The publisher independently verifies that evidence;
successful caller jobs alone cannot establish acceptance. Missing evidence and
first-stable bootstrap remain closed. Package qualification, coordinated consumer
acceptance and runtime deployment remain separate.

## Retirement and profile owner APIs

`tenant_membership` now provides caller-transaction identity locking, immutable
retirement markers and exact retirement reads. When enforcement is explicitly
enabled, membership creation checks the canonical marker before creating any
membership in any tenant. Opaque subjects are never trimmed into another identity.
`account_profile` owns scope-bound membership disablement and personal profile
erasure while preserving financial records, other people and company assets.
Helpers do not authorize HTTP callers, commit transactions or choose tenant GUCs.

The database dependency is pinned to the reconciled closure migration revision.
With a disposable TEST_DATABASE_URL, all 25 package cases exercise real directory,
profile and retirement boundaries from source, installed wheel and rebuilt sdist.
The existing production retention/hold policy is unchanged; TEST exemption work
is separate from this dependency adoption. No flags, grants or deployment change.
## Isolated pull-request qualification

`bash scripts/check-package.sh --fixtures` uses real dependency wheels
from `tests_artifacts/dependencies`, bound to the declared full Git revisions,
locked versions and SHA-256 digests. The fixtures are excluded from wheel and
source distributions. Missing/tampered artifacts or changed pins fail validation.
Frozen registry dependencies are installed normally; private dependencies use
the verified fixture bytes without resolving Git or receiving credentials.
The separate PR workflow runs on disposable Ubuntu workers with read-only
contents. The existing main workflow still resolves the actual private Git pins
and retains its scoped credential and runner boundaries.

Package CI exports complete runtime/resource contracts from actual wheels and
binds candidate digests to those builds. Rebuilt-sdist contracts must match.
Conservative byte comparisons reject implementation-only patch changes too;
semantic compatibility, installer metadata and deployed consumers remain distinct.
The PR lane also runs directory integration against disposable PostgreSQL.

## Closure release candidate

The closure runtime changes require version 1.0.0 under the conservative
packaged-byte compatibility policy. Accepted baseline artifacts remain unchanged.
Package and disposable database checks do not establish deployed acceptance.

The DB 1.0.0 fixture is built from pending DB #11 at `482943cbcd78ffd1a3d2ad4e1088ed7ed0cdeaea`,
not a published release. Merge that owner adoption before this dependent PR.

### Actions qualification and stable publication

Main merges and workflow completion do not publish GitHub test releases. Exact
qualification files remain in Actions artifacts with finite retention. The pinned
publisher independently verifies a real immutable stable baseline and refuses
qualification snapshots, even if a caller job reports success. Existing valid
stable records are retained; no release, version change, deployment or human
approval prerequisite is introduced by this correction.
