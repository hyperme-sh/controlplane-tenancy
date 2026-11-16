# Tenancy publication preparation

The owner remains Apache-2.0, version 0.14.0. Original and rebuilt wheels check
LICENSE and NOTICE against source. Tenant filters, transaction ownership and
runtime behavior remain unchanged.

CI prepares a non-root consumer image under
`ghcr.io/hyperme-sh/controlplane-tenancy/runtime` from the qualified owner wheel,
the verified exact-source DB wheel matching the project/lock pin, and hashed
public registry dependencies. Neither source checkouts nor third-party source
archives enter the context. Installed dependency license texts are retained and
indexed by version and hash; missing texts fail preparation. Every layer is
scanned and the installed owner runtime and legal bytes are verified offline.
This library image is prepared only; it is not a standalone server or an active
GHCR publication.

History review inventories reachable origin branches, tags and HEAD, including
bounded archive members, without executing old code or rewriting refs. Hidden
or deleted refs, remote LFS data and external archives are outside the scan.
Findings are review records, not publication clearance. Secret exceptions require
exact bytes and scanner coordinates.

GHCR activation and retained-image review remain separate. TEST stays on moving
channels; integration/e2e stays nightly. No Actions uploads or visibility changes.
