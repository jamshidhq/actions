#!/usr/bin/env python3
"""Bump the version based on the latest git tag, Cargo.toml and release type.

The base version is max(latest v* tag, workspace Cargo.toml version), so the
version never goes backwards when Cargo.toml is ahead of the tags. It is then
bumped according to RELEASE_TYPE. Updates Cargo.toml in-tree for the build
(the change is NOT committed — that happens in a follow-up PR).

If EXISTING_TAG is set (a v* tag already points at the commit being
released, i.e. this is a re-run), that tag is reused and no bump happens.

Env:
    RELEASE_TYPE: major | minor | patch
    EXISTING_TAG (optional): tag already on the release commit, e.g. "v0.2.0"
Outputs:
    old_version: the base version (e.g. "0.2.0")
    new_version: the bumped version string (e.g. "0.3.0")
    tag: the git tag (e.g. "v0.3.0")
    tag_exists: "true" when EXISTING_TAG was reused, else "false"

Reads Cargo.toml from GITHUB_WORKSPACE (the caller's checkout). Works for a
single crate (`[package] version`) and a workspace root
(`[workspace.package] version`): the FIRST `version = "X.Y.Z"` line wins.

Self-test: python3 -m doctest -v scripts/bump_version.py
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))

from lib import workflow_io

VERSION_LINE = re.compile(r'^(\s*version\s*=\s*")(\d+\.\d+\.\d+)(")', re.MULTILINE)


def get_latest_tag_version():
    """Get the latest semver tag from git, or 0.0.0 if none."""
    result = subprocess.run(
        ["git", "tag", "--sort=-v:refname", "--list", "v[0-9]*"],
        capture_output=True, text=True,
    )
    for line in result.stdout.strip().splitlines():
        tag = line.strip()
        if re.match(r"^v\d+\.\d+\.\d+$", tag):
            return tag[1:]  # strip leading 'v'
    return "0.0.0"


def cargo_version(content):
    """Return the first `version = "X.Y.Z"` in Cargo.toml content, or 0.0.0.

    >>> cargo_version('[workspace.package]\\nversion = "0.1.0"\\n')
    '0.1.0'
    >>> cargo_version('[workspace]\\n')
    '0.0.0'
    """
    m = VERSION_LINE.search(content)
    return m.group(2) if m else "0.0.0"


def max_version(a, b):
    """Return the higher of two X.Y.Z versions (numeric compare).

    >>> max_version("0.0.1", "0.1.0")
    '0.1.0'
    >>> max_version("0.10.0", "0.9.9")
    '0.10.0'
    >>> max_version("1.2.3", "1.2.3")
    '1.2.3'
    """
    def key(v):
        return tuple(int(x) for x in v.split("."))
    return a if key(a) >= key(b) else b


def bump(version, release_type):
    """Bump a semver version string.

    >>> bump(max_version("0.0.1", "0.1.0"), "patch")
    '0.1.1'
    >>> bump("0.1.0", "minor")
    '0.2.0'
    >>> bump("0.1.3", "major")
    '1.0.0'
    """
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        workflow_io.error(f"Invalid version format: '{version}' (expected X.Y.Z)")
        sys.exit(1)
    major, minor, patch = [int(x) for x in version.split(".")]
    if release_type == "major":
        return f"{major + 1}.0.0"
    elif release_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif release_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        workflow_io.error(f"Unknown release type: {release_type}")
        sys.exit(1)


def set_cargo_version(content, new_version):
    """Replace the first `version = "X.Y.Z"` in Cargo.toml content.

    >>> set_cargo_version('version = "0.1.0"\\nfoo = "1.0.0"\\n', "0.1.1")
    'version = "0.1.1"\\nfoo = "1.0.0"\\n'
    """
    return VERSION_LINE.sub(
        lambda m: f"{m.group(1)}{new_version}{m.group(3)}", content, count=1,
    )


def main():
    release_type = workflow_io.require_env("RELEASE_TYPE")
    existing_tag = os.environ.get("EXISTING_TAG", "").strip()

    workspace = os.environ.get("GITHUB_WORKSPACE", os.getcwd())
    cargo_toml = os.path.join(workspace, "Cargo.toml")
    with open(cargo_toml) as f:
        content = f.read()

    if existing_tag:
        if not re.fullmatch(r"v\d+\.\d+\.\d+", existing_tag):
            workflow_io.error(f"Invalid EXISTING_TAG: '{existing_tag}'")
            sys.exit(1)
        new_version = existing_tag[1:]
        old_version = new_version
        tag = existing_tag
        print(f"Tag {tag} already points at this commit, reusing (no bump)")
    else:
        tag_version = get_latest_tag_version()
        toml_version = cargo_version(content)
        old_version = max_version(tag_version, toml_version)
        new_version = bump(old_version, release_type)
        tag = f"v{new_version}"
        print(f"Base version: max(tag {tag_version}, Cargo.toml {toml_version}) = {old_version}")
        print(f"Version bump: {old_version} -> {new_version} ({release_type})")
    print(f"Tag: {tag}")

    with open(cargo_toml, "w") as f:
        f.write(set_cargo_version(content, new_version))

    workflow_io.set_output("old_version", old_version)
    workflow_io.set_output("new_version", new_version)
    workflow_io.set_output("tag", tag)
    workflow_io.set_output("tag_exists", "true" if existing_tag else "false")


if __name__ == "__main__":
    main()
