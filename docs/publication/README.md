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
Successful main CI publishes the qualified image to the moving `runtime:test`
channel and pulls it back to verify identity. Serialized publication skips stale
main revisions. The library image is not a standalone server.

History review inventories reachable origin branches, tags and HEAD, including
bounded archive members, without executing old code or rewriting refs. Hidden
or deleted refs, remote LFS data and external archives are outside the scan.
Findings are review records, not publication clearance. Secret exceptions require
exact bytes and scanner coordinates.

Retained GHCR tags and untagged versions are inventoried and every Linux amd64
layer is reviewed without executing old images. Initial unavailable access is
reported explicitly; post-publication inventory and scans must succeed.
Deleted images and other registries are outside this review. TEST stays on moving
channels; integration/e2e stays nightly. No Actions uploads or visibility changes.

The retained-content ledger in `.github/workflows/historical-content-review.json`
binds all 392 flagged archived DB members to blob/member hashes, classifications
and retained-not-cleared dispositions. CI rejects new or altered coordinates,
bytes and dispositions. These historical payment schemas remain retained;
this review does not authorize public redistribution or rewrite old refs.
