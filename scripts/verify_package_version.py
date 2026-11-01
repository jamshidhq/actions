#!/usr/bin/env python3
"""Verify that cargo reports the release version for the package to publish.

bump_version.py rewrites the FIRST `version = "X.Y.Z"` in the root Cargo.toml.
A workspace member that pins its own `version` (instead of
`version.workspace = true`) keeps its old version, and `cargo publish` would
upload that old version. This script asks cargo, not the TOML text, and fails
on any difference.

Env:
    VERSION: the release version (e.g. "0.2.0")
    PACKAGE (optional): package name; empty means the only package in the
        workspace
Outputs:
    name: the package name
    version: the verified version (equal to VERSION)

Self-test: python3 -m doctest -v scripts/verify_package_version.py
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))

from lib import workflow_io


def resolve(metadata, package, version):
    """Return (name, version) or raise ValueError with the error message.

    >>> meta = {"packages": [{"name": "a", "version": "0.2.0"}]}
    >>> resolve(meta, "", "0.2.0")
    ('a', '0.2.0')
    >>> resolve(meta, "a", "0.3.0")
    Traceback (most recent call last):
    ...
    ValueError: version mismatch: cargo metadata reports a 0.2.0, the release is 0.3.0. Does the package pin its own version instead of version.workspace = true?
    >>> resolve(meta, "b", "0.2.0")
    Traceback (most recent call last):
    ...
    ValueError: package 'b' is not in the workspace (packages: a)
    >>> two = {"packages": [{"name": "a", "version": "1.0.0"},
    ...                     {"name": "b", "version": "1.0.0"}]}
    >>> resolve(two, "", "1.0.0")
    Traceback (most recent call last):
    ...
    ValueError: workspace has 2 packages; set the `package` input
    """
    packages = metadata["packages"]
    if not package:
        if len(packages) != 1:
            raise ValueError(
                f"workspace has {len(packages)} packages; set the `package` input"
            )
        package = packages[0]["name"]
    matches = [p for p in packages if p["name"] == package]
    if not matches:
        names = ", ".join(sorted(p["name"] for p in packages))
        raise ValueError(
            f"package '{package}' is not in the workspace (packages: {names})"
        )
    actual = matches[0]["version"]
    if actual != version:
        raise ValueError(
            f"version mismatch: cargo metadata reports {package} {actual}, "
            f"the release is {version}. Does the package pin its own version "
            f"instead of version.workspace = true?"
        )
    return package, actual


def main():
    version = workflow_io.require_env("VERSION")
    package = os.environ.get("PACKAGE", "").strip()
    out = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--no-deps"],
        check=True, capture_output=True, text=True,
    ).stdout
    try:
        name, verified = resolve(json.loads(out), package, version)
    except ValueError as exc:
        workflow_io.error(str(exc))
        sys.exit(1)
    print(f"cargo metadata: {name} {verified} (matches the release)")
    workflow_io.set_output("name", name)
    workflow_io.set_output("version", verified)


if __name__ == "__main__":
    main()
