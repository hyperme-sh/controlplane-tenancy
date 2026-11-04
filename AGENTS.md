# Tenancy library development

Own shared tenant session/GUC helpers, membership, directory and registry APIs.
HTTP authorization, provider proof and audit remain with calling services.
Preserve tenant filters, detached copy-isolated views, row locks and caller-owned
transactions. Never import product or legacy implementation modules.

Run `bash scripts/check-package.sh`; set `TEST_DATABASE_URL` only to a disposable
PostgreSQL instance for directory integration cases. The fixture creates and drops
a unique test database and applies only platform migrations there. Private database
package read access must be provided externally, never stored in source or wheels.

## Package publication permission boundary

Source/package validation keeps its existing runner policy and read-only contents.
The separate `.github/workflows/release.yml` publication job is the narrow exception:
it may use `contents: write` and `actions: read` on disposable `ubuntu-24.04` workers
solely through the exact-pinned shared package publisher. It must not check out or
execute this repository's code, install its packages, or receive private dependency
or deployment credentials. This hosted publication exception does not authorize
moving secret-bearing validation to another runner group. Stable publication must
retain any configured release-admission prerequisite for the exact tag/commit.
