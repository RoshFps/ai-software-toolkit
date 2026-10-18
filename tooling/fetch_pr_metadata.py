#!/usr/bin/env python3
"""Fetch candidate Git objects, never a candidate checkout or executable runtime."""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit


MAX_POLICY_BYTES = 1024 * 1024


def git(root: Path, *args: str, env: dict[str, str] | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], env=env, capture_output=True, timeout=240,
    )
    if result.returncode:
        # Remote diagnostics can contain credentials or attacker-controlled text.
        raise ValueError("candidate Git metadata operation failed")
    return result.stdout


def fetch(root: Path, repository: str, server: str, base: str, head: str, pr: str, token: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("invalid repository")
    url = urlsplit(server)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
        raise ValueError("invalid GitHub server URL")
    if not all(re.fullmatch(r"[0-9a-f]{40}", value) for value in (base, head)):
        raise ValueError("invalid commit SHA")
    if pr and not re.fullmatch(r"[1-9][0-9]*", pr):
        raise ValueError("invalid pull-request number")
    root.mkdir()  # Refuse reuse, including pre-existing symlinks/config/hooks.
    git(root, "init", "--bare")
    env = os.environ.copy()
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    env["GIT_CONFIG_COUNT"] = "3"
    env["GIT_CONFIG_KEY_0"] = "credential.helper"
    env["GIT_CONFIG_VALUE_0"] = ""
    env["GIT_CONFIG_KEY_1"] = "http.followRedirects"
    env["GIT_CONFIG_VALUE_1"] = "false"
    env["GIT_CONFIG_KEY_2"] = "http.extraHeader"
    env["GIT_CONFIG_VALUE_2"] = "AUTHORIZATION: basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode()
    remote = f"{server.rstrip('/')}/{repository}.git"
    # GitHub exposes fork PR heads in the base repository, including private repos.
    # Full ancestry is needed for merge-base scope calculation.
    git(root, "fetch", "--no-tags", "--no-recurse-submodules", remote,
        f"{base}:refs/proof/base", f"{('refs/pull/' + pr + '/head') if pr else head}:refs/proof/head", env=env)
    for ref, expected in (("base", base), ("head", head)):
        if git(root, "rev-parse", f"refs/proof/{ref}^{{commit}}").decode().strip() != expected:
            raise ValueError("candidate revision changed during metadata fetch")


def policy(root: Path, head: str, output: Path) -> None:
    # Traverse exact tree entries, rejecting symlinks, gitlinks and executable files.
    tree = git(root, "ls-tree", "-z", head, "--", ".proof")
    if not re.fullmatch(rb"040000 tree [0-9a-f]{40}\t\.proof\x00", tree):
        raise ValueError("candidate .proof must be a tree")
    entry = git(root, "ls-tree", "-z", f"{head}:.proof", "--", "policy.yaml")
    match = re.fullmatch(rb"100644 blob ([0-9a-f]{40})\tpolicy\.yaml\x00", entry)
    if not match:
        raise ValueError("candidate policy must be a regular non-executable blob")
    oid = match[1].decode()
    size = int(git(root, "cat-file", "-s", oid))
    if not 0 < size <= MAX_POLICY_BYTES:
        raise ValueError("candidate policy exceeds the supported size")
    data = git(root, "cat-file", "blob", oid)
    output.parent.mkdir(parents=True, exist_ok=False)
    output.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--policy-output", type=Path)
    args = parser.parse_args()
    try:
        fetch(args.repository_root, os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SERVER_URL"],
              os.environ["BASE_SHA"], os.environ["HEAD_SHA"], os.environ.get("PR_NUMBER", ""), os.environ["GH_TOKEN"])
        if args.policy_output:
            policy(args.repository_root, os.environ["HEAD_SHA"], args.policy_output)
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"Metadata fetch failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
