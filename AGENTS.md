# Tenancy library development

Own shared tenant session/GUC helpers, membership, directory and registry APIs.
HTTP authorization, provider proof and audit remain with calling services.
Preserve tenant filters, detached copy-isolated views, row locks and caller-owned
transactions. Never import product or legacy implementation modules.

Run `bash scripts/check-package.sh`; set `TEST_DATABASE_URL` only to a disposable
PostgreSQL instance for directory integration cases. The fixture creates and drops
a unique test database and applies only platform migrations there. Private database
package read access must be provided externally, never stored in source or wheels.
