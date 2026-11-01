"""GitHub Actions I/O helpers."""

import os
import sys


def set_output(key, value):
    """Write a step output to $GITHUB_OUTPUT."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        print(
            f"WARNING: GITHUB_OUTPUT not set, would output {key}={value}",
            file=sys.stderr,
        )
        return
    with open(output_file, "a") as f:
        f.write(f"{key}={value}\n")


def error(msg):
    """Emit a GitHub Actions error annotation."""
    print(f"::error::{msg}")


def require_env(name):
    """Get a required environment variable or exit."""
    val = os.environ.get(name)
    if not val:
        error(f"Required environment variable {name} is not set")
        sys.exit(1)
    return val
