# Releasing controlplane-tenancy

This page is the release-channel reference for the 0.14.0 tree. The README
keeps only the version pointer.

## Package version

`pyproject.toml` declares `controlplane-tenancy` **0.14.0**.
[`release-policy.json`](../release-policy.json) sets the release line to
`0.14`. The direct database dependency is

```text
controlplane-db @ git+https://github.com/hyperme-sh/controlplane-db.git@95ef61433374274f4a4fc287e15982be6357e1cc
```

which is `controlplane-db` 0.1.0. `sqlalchemy` is `>=2.0.43`. The lockfile
resolves SQLAlchemy 2.1.6, `asyncpg` 0.32.0, and `psycopg` 3.3.6.

Two published GitHub tags do not share that metadata:

| Tag | Commit | Package version | `controlplane-db` pin |
| --- | --- | --- | --- |
| `0.24.0-test.0` (prerelease) | `c6405dcb6612899cd8b36f3c01e051821f9522ed` | 0.14.0 | `95ef61433374274f4a4fc287e15982be6357e1cc` |
| `v0.24.0` | `bbebecc933413658a13b0e9e55b118bef6d2032b` | 0.24.0 | `6ee52fe3e775548956cada649715fdde80f6cd1d` |

`0.24.0-test.0` matches the `main` commit documented here. `v0.24.0` is an
earlier tree. Install the default branch or the `0.24.0-test.N` tag when you
want the 0.14.0 package this repository builds today.

## Main qualification

A push to `main` runs [`.github/workflows/package.yml`](../.github/workflows/package.yml)
(Standalone package) on Python 3.13 and uv 0.11.26 with disposable PostgreSQL
17. The job runs `bash scripts/check-package.sh` and uploads the exact wheel
and sdist as the Actions artifact `tested-dist` (90-day retention, uncompressed).
That workflow does not create a GitHub release or a tag.

Pull requests run [`.github/workflows/consumer-qualification.yml`](../.github/workflows/consumer-qualification.yml)
with `bash scripts/check-package.sh --fixtures`. That lane does not publish.

## Coordinated test bundles

[`.github/test-channel.json`](../.github/test-channel.json) sets `"next"` to
`0.24.0`. After a successful `main` push of Standalone package,
[`.github/workflows/test-bundles.yml`](../.github/workflows/test-bundles.yml)
publishes the retained `tested-dist` bytes as an immutable prerelease named
`0.24.0-test.N`.

The job calls the pinned publisher
`hyperme-sh/.github/actions/bundle-channel@2f4d291a3e833520b7a8c5cb5e5cbc812395f691`
with `mode: test`. The publisher checks the workflow run, the source revision,
the channel configuration, and the original artifact digest. It does not check
out this repository, run its code, or receive the database-dependency
credential. A pull request does not publish. A missing artifact or a name
collision fails the job.

The `0.24.0-test.N` name is the train id. The wheel's project version stays
0.14.0. Consumers bind a bundle by its tag, commit, and the digest in that
release's manifest. A test bundle is not a stable release. `0.24.0-test.0` is
the bundle built from `c6405dcb6612899cd8b36f3c01e051821f9522ed`.

## Qualification snapshot tags

Tags named `test-<40-character commit sha>` are earlier qualification
prereleases. They remain on the repository as evidence for those commits.
They are not the stable channel, and they do not reserve the version embedded
in the wheel.

## Stable tags

A tag matching `v*` runs [`.github/workflows/release.yml`](../.github/workflows/release.yml).

1. Admission calls
   `hyperme-sh/spanopticon/.github/workflows/component-release.yml@32c064be9fe47e230e0d48d353ada8b38a7c1644`
   with `release-line: 0.14`, `baseline-ref` set from the repository variable
   `SPANOPTICON_RELEASE_BASELINE_SHA`, and `requested-version` set from the tag.
2. When admission succeeds, publication calls
   `hyperme-sh/.github/actions/release-channel@c16044a6d987d7d912d70bcd09ea731ab2b91b9e`
   for `.github/workflows/package.yml`. The action publishes the exact
   `tested-dist` artifact from the qualifying run. It does not rebuild the
   package from the tag by checking out and executing this repository.

`releases/accepted/release.json` is the accepted baseline record.
`releases/candidate/release.json` is the candidate for line `0.14`, package
`0.14.0`. The accepted file currently records line `0.24` and version
`0.24.0`, which matches the earlier `v0.24.0` tag and does not match the
0.14.0 candidate. Admission compares those records, the tag, and the artifact
digests before publication. A green Standalone package or test-bundle job
does not publish a stable release.

Manifest layout and compatibility checks are described in
[release-policy.md](release-policy.md) and in the
[Spanopticon release notes](https://github.com/hyperme-sh/spanopticon/blob/main/docs/releases.md).
The line this repository configures in `release-policy.json` and in
`release.yml` is `0.14`.
