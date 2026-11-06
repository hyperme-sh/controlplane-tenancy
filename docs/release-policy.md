# Release compatibility

Channel publication for this repository is documented in
[releasing.md](releasing.md). The configured line in `release-policy.json` and
`.github/workflows/release.yml` is **0.14**, matching package version 0.14.0.
A patch on that line keeps the accepted API contract. Installing the workflow
does not publish a release.

`release-policy.json` names the component and the version file
(`pyproject.toml`). The pinned Spanopticon workflow checks that file on pull
requests. A version change or a `releases/candidate/release.json` submission
also runs admission. A tag push and a manual release request run admission
too. A configuration-only result is not a compatibility result.

Before a stable tag:

1. Put an accepted bundle at `releases/accepted/release.json`, with its
   contract files and immutable artifact references. Set the repository
   variable `SPANOPTICON_RELEASE_BASELINE_SHA` to that baseline's full
   40-character commit SHA. The baseline comes from a real qualification run
   and its provenance. Example digests are not release evidence.
2. Generate `releases/candidate/release.json` from the release artifacts. The
   candidate contains this component only, uses line `0.14`, and matches
   `pyproject.toml` plus the requested tag.
3. Run admission against the baseline. The patch contract stays unchanged.
   Replacing the bytes of an artifact already published at the same version
   is rejected. Check artifact provenance and downstream consumer behavior
   separately.
4. The `v*` publisher runs that admission, and the artifact check, for the
   exact tag before it publishes. The baseline is selected from
   `SPANOPTICON_RELEASE_BASELINE_SHA`, not from the candidate file. Keep the
   validation evidence with the run.

A missing baseline stops admission. The workflow does not publish, deploy,
enable repository Actions, or grant database-dependency access. Manifest
fields are specified in the
[Spanopticon release notes](https://github.com/hyperme-sh/spanopticon/blob/main/docs/releases.md).
