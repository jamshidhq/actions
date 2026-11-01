#!/usr/bin/env python3
"""Create a PR to update Cargo.toml version and CHANGELOG after a release.

This runs after a successful release. It creates a branch with the
version bump and changelog update, then opens a PR labeled 'no-release'.

GitHub gotcha: a PR opened with the workflow's GITHUB_TOKEN does NOT
trigger other workflows, so ci.yaml does not run on the bump PR. See the
comment on the "Create version bump PR" step in rust-release.yaml.

Env:
    GITHUB_REPOSITORY: owner/repo
    GITHUB_TOKEN: token with contents:write + pull-requests:write
    GITHUB_SERVER_URL (optional): defaults to https://github.com
    TAG: version tag that was just released (e.g. "v0.2.0")
    NEW_VERSION: version string (e.g. "0.2.0")
    BASE_BRANCH: the caller's default branch, the bump PR's base (e.g. "main")
    CLIFF_CONFIG (optional): git-cliff config path; defaults to git-cliff's own
"""

import base64
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))

from lib import workflow_io

BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def normalize_changelog(text):
    """Return `text` ending in exactly one newline (empty stays empty).

    git-cliff keeps the blank lines a body template ends with, so the file can
    end in "\\n\\n". The caller's end-of-file-fixer hook then fails CI on the
    bump PR.

    >>> normalize_changelog("# Changelog\\n\\n## [1.0.0]\\n\\n- a\\n\\n")
    '# Changelog\\n\\n## [1.0.0]\\n\\n- a\\n'
    >>> normalize_changelog("- a\\n\\n\\n\\n")
    '- a\\n'
    >>> normalize_changelog("- a")
    '- a\\n'
    >>> normalize_changelog("- a\\n")
    '- a\\n'
    >>> normalize_changelog("\\n\\n")
    ''
    """
    stripped = text.rstrip()
    return stripped + "\n" if stripped else ""


def run(cmd, **kwargs):
    """Run a command, printing it first."""
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def main():
    repo = workflow_io.require_env("GITHUB_REPOSITORY")
    token = workflow_io.require_env("GITHUB_TOKEN")
    tag = workflow_io.require_env("TAG")
    new_version = workflow_io.require_env("NEW_VERSION")
    base_branch = workflow_io.require_env("BASE_BRANCH")
    cliff_config = os.environ.get("CLIFF_CONFIG", "").strip()
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    host = server.split("://", 1)[-1]

    branch = f"chore/bump-{tag}"

    # A bump PR for this tag was already merged: nothing to do. Checked first,
    # because it still answers after the merged branch has been deleted.
    merged = subprocess.run(
        ["gh", "pr", "list", "--repo", repo, "--head", branch, "--state", "merged",
         "--json", "number", "--jq", ".[].number"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    if merged:
        print(f"Bump PR #{merged[0]} for {branch} was already merged, nothing to do")
        return

    # Configure git (checkout ran with persist-credentials: false). Auth goes
    # through per-process git config env, so the token never lands in
    # .git/config.
    run(["git", "config", "--local", "user.email", BOT_EMAIL])
    run(["git", "config", "--local", "user.name", BOT_NAME])
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    os.environ.update({
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"http.https://{host}/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {auth}",
    })

    # Idempotent re-run: reuse an existing bump branch / PR instead of failing.
    branch_exists = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", f"refs/heads/{branch}"],
        capture_output=True,
    ).returncode == 0

    if branch_exists:
        print(f"Branch {branch} already exists on remote, reusing it")
    else:
        # Fetch the latest default branch (the release tag commit)
        run(["git", "fetch", "origin", base_branch])
        run(["git", "checkout", "-b", branch, f"origin/{base_branch}"])

        # Update Cargo.toml version
        cargo_toml = "Cargo.toml"
        with open(cargo_toml) as f:
            content = f.read()
        updated = re.sub(
            r'^(\s*version\s*=\s*")(\d+\.\d+\.\d+)(")',
            lambda m: f"{m.group(1)}{new_version}{m.group(3)}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        with open(cargo_toml, "w") as f:
            f.write(updated)

        # Sync Cargo.lock with the new workspace version (members only)
        run(["cargo", "update", "--workspace"])

        # Update CHANGELOG
        cliff_cmd = ["git-cliff", "--output", "CHANGELOG.md"]
        if cliff_config:
            cliff_cmd += ["--config", cliff_config]
        result = subprocess.run(
            cliff_cmd,
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"git-cliff failed: {result.stderr}")
            print("Skipping changelog update")
        else:
            with open("CHANGELOG.md") as f:
                changelog = f.read()
            with open("CHANGELOG.md", "w") as f:
                f.write(normalize_changelog(changelog))

        # Commit and push
        run(["git", "add", "Cargo.toml", "Cargo.lock", "CHANGELOG.md"])
        run(["git", "commit", "-m", f"chore(release): bump version to {tag}"])
        run(["git", "push", "origin", branch])

    # Reuse an existing PR for this branch if there is one
    existing = subprocess.run(
        ["gh", "pr", "list", "--repo", repo, "--head", branch, "--state", "all",
         "--json", "number,state", "--jq", ".[] | \"\\(.number) \\(.state)\""],
        check=True, capture_output=True, text=True,
    ).stdout.split("\n")
    prs = [line.split() for line in existing if line.strip()]
    open_prs = [n for n, state in prs if state == "OPEN"]
    if any(state == "MERGED" for _, state in prs) and not open_prs:
        print(f"Bump PR for {branch} was already merged, nothing to do")
        return

    if open_prs:
        pr_number = open_prs[0]
        print(f"Bump PR #{pr_number} already open, reusing it")
    else:
        # Create PR (gh reads GH_TOKEN, falling back to GITHUB_TOKEN)
        print(f"Creating bump PR for {tag}")
        body = (
            f"Automated post-release PR.\n\n"
            f"- Updates `Cargo.toml` version to `{new_version}` (and `Cargo.lock`)\n"
            f"- Updates `CHANGELOG.md` via git-cliff\n\n"
            f"This PR was created by the release workflow after tagging `{tag}`."
        )
        pr = subprocess.run(
            ["gh", "pr", "create", "--repo", repo,
             "--base", base_branch, "--head", branch,
             "--title", f"chore(release): bump version to {tag}",
             "--body", body],
            check=True, capture_output=True, text=True,
        )
        pr_url = pr.stdout.strip().splitlines()[-1] if pr.stdout.strip() else ""
        match = re.search(r"/pull/(\d+)$", pr_url)
        if not match:
            workflow_io.error(f"Could not parse PR number from gh output: {pr.stdout!r}")
            sys.exit(1)
        pr_number = match.group(1)
        print(f"PR created: #{pr_number}")

    # Add no-release label (the issues API creates the label if it is missing)
    label = subprocess.run(
        ["gh", "api", "--method", "POST",
         f"repos/{repo}/issues/{pr_number}/labels",
         "-f", "labels[]=no-release"],
        capture_output=True, text=True,
    )
    if label.returncode == 0:
        print("Added 'no-release' label")
    else:
        print(f"WARNING: failed to add 'no-release' label, add it manually: {label.stderr}")

    print(f"\nBump PR: {server}/{repo}/pull/{pr_number}")


if __name__ == "__main__":
    main()
