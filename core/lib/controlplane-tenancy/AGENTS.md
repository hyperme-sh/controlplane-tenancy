# controlplane-tenancy package context

This shared package owns its implementations and the compatibility exports from
legacy api modules. Read README.md and the exact public modules in
scripts/import_boundaries.json and scripts/ownership.json before editing.
Keep product and legacy api implementation imports out of this package.
Update the shared contract snapshots/version for public API changes.
Run the shared suite and affected service suites; installed-wheel and legacy
alias tests belong in core/tests/tests/unit/test_identity_tenancy_libraries.py.
