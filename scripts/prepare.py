#!/usr/bin/env python3
"""Fetch the pinned upstream source and apply only this repository's patch."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def git(source, *args):
    return subprocess.check_output(
        ["git", "-C", str(source), *args], stderr=subprocess.PIPE
    )


def prepare(source, package):
    spec = json.loads((package / "source.json").read_text())
    patch = package / spec["patch"]
    content = patch.read_bytes()
    if hashlib.sha256(content).hexdigest() != spec["sha256"]:
        raise ValueError("Patch checksum mismatch; no source was changed")
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", "--branch", spec["ref"],
             spec["repository"], str(source)], check=True
        )
    if git(source, "rev-parse", "HEAD").decode().strip() != spec["commit"]:
        raise ValueError("Source is not the pinned upstream commit; use a fresh directory")
    diff = git(source, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD")
    untracked = git(source, "ls-files", "--others", "--exclude-standard")
    if diff == content and not untracked.strip():
        return source
    if diff or untracked.strip():
        raise ValueError("Source contains other changes; nothing was overwritten")
    git(source, "apply", "--check", "--index", str(patch))
    git(source, "apply", "--index", str(patch))
    return source


def main():
    package = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=package / ".build/herdr")
    args = parser.parse_args()
    try:
        print(prepare(args.source.expanduser().resolve(), package))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"prepare: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
