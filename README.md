# jamshidhq/actions

Reusable GitHub Actions workflows for jamshidhq Rust crates. They are
extracted from the reviewed CI and release workflows of `jamshidhq/jamshid`
and generalised for single-crate library repositories.

| Workflow | Purpose |
| --- | --- |
| `.github/workflows/rust-ci.yaml` | PR checks: release label, pre-commit, `cargo fmt`, `cargo clippy -D warnings`, `cargo test`, cargo-deny, typos, actionlint, zizmor |
| `.github/workflows/rust-release.yaml` | Label-driven release on merge: version bump, git-cliff notes, tag, GitHub release, bump PR, optional crates.io publish |
| `.github/workflows/ci.yaml` | Self-test of this repository: runs both workflows against `tests/fixture-crate` on every PR (release in dry-run mode) |

## Caller example

Pin by full commit SHA. Use the same SHA for both workflows.

```yaml
# .github/workflows/ci.yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, labeled, unlabeled]
permissions:
  contents: read
jobs:
  ci:
    uses: jamshidhq/actions/.github/workflows/rust-ci.yaml@<40-hex-sha>  # vX.Y.Z
```

```yaml
# .github/workflows/release.yaml  (crates.io trusted publisher: "release.yaml")
on:
  pull_request:
    types: [closed]
    branches: [main]
  workflow_dispatch:
    inputs:
      pr_number: { type: string, required: true }
permissions:
  contents: read
jobs:
  release:
    permissions:
      contents: write        # tag, release, bump branch
      pull-requests: write   # bump PR
      id-token: write        # crates.io trusted publishing
    uses: jamshidhq/actions/.github/workflows/rust-release.yaml@<40-hex-sha>  # vX.Y.Z
    with:
      pr_number: ${{ github.event.pull_request.number || inputs.pr_number }}
      publish: true
    secrets:
      actions_read_token: ${{ secrets.JAMSHIDHQ_ACTIONS_READ_TOKEN }}
```

Path filters, triggers and concurrency stay in the caller. Never pass
`secrets: inherit`; pass named secrets only.

## rust-ci.yaml inputs

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `toolchain` | string | `""` | Rust toolchain. Empty: the caller's `rust-toolchain.toml` |
| `feature_args` | string | `--all-features` | Feature flags for `cargo clippy` and `cargo test` |
| `apt_packages` | string | `""` | Space-separated apt packages the crate needs to build |
| `check_release_label` | boolean | `true` | Require exactly one of `major`/`minor`/`patch`/`no-release` on PR events |
| `run_tests` | boolean | `true` | Run `cargo test` |

No secrets. The job needs `contents: read`.

Pinned tools: cargo-deny 0.20.2, typos 1.51.1, zizmor 1.29.0, actionlint
1.7.12, gitleaks 8.30.1, pre-commit 4.7.0. cargo-deny, gitleaks and
actionlint must equal the versions in `yadgarhq/actions` `versions.yaml` at
the hook `rev` callers use, because those hooks refuse other versions.

## rust-release.yaml inputs and secrets

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `pr_number` | string | `""` | Merged PR to release |
| `default_branch` | string | `main` | The PR base must be this branch; the bump PR targets it |
| `publish` | boolean | `false` | Publish to crates.io with trusted publishing |
| `package` | string | `""` | Package to publish. Empty: the only package in the workspace |
| `environment` | string | `""` | GitHub environment for the publish job |
| `release_name_prefix` | string | `""` | Prefix for the GitHub release title |
| `toolchain` | string | `""` | Rust toolchain. Empty: the caller's `rust-toolchain.toml` |
| `apt_packages` | string | `""` | Apt packages for `cargo update` / `cargo publish` |
| `dry_run` | boolean | `false` | Compute version and notes, run `cargo publish --dry-run`, write nothing |
| `dry_run_release_type` | string | `minor` | Release type to simulate in a dry run |

| Secret | Required | Meaning |
| --- | --- | --- |
| `actions_read_token` | no | Read access to `jamshidhq/actions`. Needed while this repository is private and the caller is another repository (see below) |

Output: `tag`, the released tag.

### How a release works

1. `decide` reads the PR. It needs exactly one release label. `no-release`
   and closed-unmerged PRs stop here. A PR merged into another branch fails.
2. `release` runs under job-level concurrency group `release`. It:
   - reuses a `vX.Y.Z` tag that already points at the merge commit (re-run);
   - skips the whole release when a later tag already contains the merge
     commit (a dropped pending run shipped in that later release);
   - computes the version as max(latest `vX.Y.Z` tag, first `version =` in
     the root `Cargo.toml`) bumped by the label;
   - writes notes with `git-cliff --unreleased --tag` (`--current` on re-run),
     using the caller's `cliff.toml` or the default in this repository;
   - pushes an annotated tag, and refuses if the tag exists on another commit;
   - creates or updates the GitHub release;
   - opens a `no-release` bump PR with `Cargo.toml`, `Cargo.lock` and
     `CHANGELOG.md`, and reuses an existing branch or PR.
3. `crate` (only with `publish: true`) rewrites `Cargo.toml` to the released
   version and checks crates.io. An existing version is skipped, so a re-run
   is safe. Otherwise it gets a token from
   `rust-lang/crates-io-auth-action@3268eb413133e2960fa4ae0e963ca76380c54cd9`
   (v1.0.6) and runs `cargo publish`.

Caller repository settings: enable "Allow GitHub Actions to create and approve
pull requests". Create the four labels. Commit `Cargo.lock`. The bump PR does
not get CI, because a PR opened with `GITHUB_TOKEN` triggers no workflows.
Close and reopen it to run CI.

Deviation from jamshid: jamshid has a read-only build job and a separate
write publish job. A library has no build artefact, so one `release` job holds
the write scopes. The crates.io publish is a separate job with only
`contents: read` and `id-token: write`.

## How the workflows load their scripts

A reusable workflow runs in the caller's workspace. It cannot read files from
its own repository. The options:

| Option | Result |
| --- | --- |
| Composite actions, `uses: jamshidhq/actions/actions/<name>@<sha>` | Not possible to pin correctly. `uses:` inside a workflow must be a literal, so the workflow cannot name its own commit. A literal SHA is always one commit behind and needs a second PR per change. `@main` is a moving ref that breaks the caller's SHA pin |
| Check out `jamshidhq/actions` at `job.workflow_sha` (chosen) | Scripts always come from the exact commit the caller pinned. No drift, one PR per change. While the repository is private, a cross-repository checkout needs a token |

`rust-release.yaml` checks out `jamshidhq/actions` at `job.workflow_sha`. It
fails when that value is not a 40-hex SHA, with no fallback to a branch. The
checkout moves out of the caller's tree to `$RUNNER_TEMP`, so it never enters
a commit or a crate package. `rust-ci.yaml` needs no scripts.

Private-repository access:

- Repository setting Actions > Access is "organization". Other jamshidhq
  repositories can then call these workflows.
- That setting does not let a caller's `GITHUB_TOKEN` clone this repository.
  Until this repository is public, give `actions_read_token`: a fine-grained
  token or GitHub App token with `contents: read` on `jamshidhq/actions` only.
- The self-test in this repository needs no token.
- After the repository is public, `actions_read_token` can be dropped.

## crates.io trusted publishing

Facts from the crates.io documentation and source (`rust-lang/crates.io`
at `9839ef7bf9b776dcd322a9765ab3d2809faf45ea`):

- The first publish of each crate needs an API token. The crate owner does
  that once by hand. Then add the trusted publisher in the crate's
  settings on crates.io.
- crates.io matches the `workflow_ref` claim, which names the CALLER's
  top-level workflow. Set the "Workflow filename" to the caller's file (e.g.
  `release.yaml`), not `rust-release.yaml`.
- If you set the `environment` input, set the same environment on crates.io.
- crates.io refuses `pull_request_target` and `workflow_run` events.
  `pull_request` (closed) and `workflow_dispatch` are accepted.
- A public repository is not required. The token exchange does not read the
  `repository_visibility` claim, and the docs list no visibility condition.
  A private source repository can publish. The published crate itself is
  public.

## Development

```sh
pre-commit install --hook-type pre-commit --hook-type commit-msg
pre-commit run --all-files
python3 -m doctest -v scripts/bump_version.py
cargo test --workspace --all-features
actionlint && zizmor --offline .github
```

The root `Cargo.toml` is a virtual workspace for the fixture crate only. It
lets the shared cargo hooks run at the repository root.
