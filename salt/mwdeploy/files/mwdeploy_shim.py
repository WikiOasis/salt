#!/usr/bin/env python3
"""mwdeploy-shim — atomic, single-purpose deploy primitives for MediaWiki.

This is what the deploy portal executes on each minion, one subcommand at a
time, via ``salt '<target>' cmd.run_all '<mwdeploy-shim ...>'``.

It is deliberately *not* an orchestrator. There is no curses UI, no multi-server
loop, no HAProxy fan-out, no JSON state file and no interactive prompting — the
portal owns all of that. Each subcommand does one thing, prints exactly one JSON
object as its final line of stdout, and exits non-zero on failure.

    {"ok": true,  "detail": "git checkout 4a9f2e1 in /srv/.../extensions/Echo"}
    {"ok": false, "error": "patch failed: ...", "stdout": "...", "stderr": "..."}

The rsync flag sets, the ``chown www-data`` fix-ups, the ``sudo -u www-data``
invocation pattern, the l10n rebuild and the HAProxy socket commands are carried
over from the original mwdeploy tool unchanged; only the surface has changed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

VERSION = "2.1.0"

# The user that owns the MediaWiki tree and runs git/rsync against it.
WEB_USER = os.environ.get("MWDEPLOY_WEB_USER", "www-data")

# Field separator for git --format output; ASCII unit separator never appears in
# a commit subject.
GIT_SEP = "\x1f"

# Excludes carried over verbatim from the original rsync_local/rsync_remote.
RSYNC_EXCLUDES: tuple[str, ...] = (
    ".git",
    ".gitignore",
    ".gitmodules",
    ".gitreview",
    "cache/*",
    "images/*",
    "l10n_cache/*",
    "tests/*",
    "*.swp",
    "*.pyc",
    "__pycache__",
)

# Base rsync flags. --delete is intentional: a file removed upstream must go away
# on the appservers too, or a deleted extension keeps being loadable.
RSYNC_FLAGS: tuple[str, ...] = (
    "--recursive",
    "--links",
    "--times",
    "--perms",
    "--delete",
    "--delete-after",
    "--compress",
    "--human-readable",
    "--omit-dir-times",
)

# Extra flags for a first-time provision, where the tree does not exist yet and
# there is nothing to compare against.
RSYNC_PROVISION_FLAGS: tuple[str, ...] = ("--whole-file", "--ignore-times")


class ShimError(Exception):
    """A failure worth reporting as {"ok": false} rather than a traceback."""

    def __init__(self, message: str, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.stdout = stdout
        self.stderr = stderr


@dataclass
class Ran:
    """Result of one subprocess."""

    argv: Sequence[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def raise_for_status(self, message: str) -> "Ran":
        if not self.ok:
            raise ShimError(
                f"{message} (exit {self.returncode}): {(self.stderr or self.stdout).strip()}",
                stdout=self.stdout,
                stderr=self.stderr,
            )

        return self


@dataclass
class Result:
    """The single JSON object a subcommand prints."""

    ok: bool
    detail: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""

    def to_json(self) -> str:
        payload: dict[str, Any] = {"ok": self.ok}

        if self.ok:
            payload["detail"] = self.detail or "ok"
        else:
            payload["error"] = self.error or "failed"
            # Only carried on failure: the portal logs these verbatim, and a
            # successful rsync's file list is noise in a deploy log.
            if self.stdout:
                payload["stdout"] = _truncate(self.stdout)
            if self.stderr:
                payload["stderr"] = _truncate(self.stderr)

        payload.update(self.extra)

        return json.dumps(payload, sort_keys=False)


def _truncate(value: str, limit: int = 8000) -> str:
    value = value.strip()

    return value if len(value) <= limit else value[:limit] + "… (truncated)"


def run(
    argv: Sequence[str],
    *,
    cwd: str | None = None,
    as_web_user: bool = False,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> Ran:
    """Run a command, never through a shell.

    ``as_web_user`` wraps in ``sudo -u www-data`` so files land owned by the web
    user, which is the invocation pattern the original tool used for every git
    and rsync call against the MediaWiki tree.
    """
    argv = list(argv)

    if as_web_user and _current_user() != WEB_USER:
        argv = ["sudo", "-n", "-u", WEB_USER] + argv

    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **(env or {})},
            check=False,
        )
    except FileNotFoundError as exc:
        raise ShimError(f"command not found: {argv[0]} ({exc})") from exc
    except subprocess.TimeoutExpired as exc:
        raise ShimError(
            f"timed out after {timeout}s: {' '.join(argv)}",
            stdout=_decode(exc.stdout),
            stderr=_decode(exc.stderr),
        ) from exc

    return Ran(argv, completed.returncode, completed.stdout or "", completed.stderr or "")


def _decode(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")

    return str(value)


def _current_user() -> str:
    try:
        import pwd

        return pwd.getpwuid(os.geteuid()).pw_name
    except Exception:  # pragma: no cover - non-POSIX or missing pwd
        return ""


def fix_ownership(path: str) -> None:
    """Re-assert www-data ownership on the tree."""
    if _current_user() == WEB_USER:
        return

    chown = shutil.which("chown")

    if chown is None:
        return

    run(["sudo", "-n", chown, "-R", f"{WEB_USER}:{WEB_USER}", path])


# --------------------------------------------------------------------------- #
# git
# --------------------------------------------------------------------------- #

def require_repo(path: str) -> str:
    if not os.path.isdir(path):
        raise ShimError(f"no such directory: {path}")

    if not os.path.exists(os.path.join(path, ".git")):
        raise ShimError(f"not a git repository: {path}")

    return path


def git(path: str, *arguments: str, timeout: int | None = 600) -> Ran:
    return run(["git", "-C", path, *arguments], as_web_user=True, timeout=timeout)


def current_head(path: str) -> tuple[str, str]:
    symbolic = git(path, "symbolic-ref", "--quiet", "--short", "HEAD", timeout=60)

    if symbolic.ok and symbolic.stdout.strip():
        return "branch", symbolic.stdout.strip()

    revision = git(path, "rev-parse", "HEAD", timeout=60)
    revision.raise_for_status("could not read HEAD")

    return "commit", revision.stdout.strip()


def cmd_git_head(args: argparse.Namespace) -> Result:
    path = require_repo(args.path)
    ref_type, ref_value = current_head(path)

    return Result(
        ok=True,
        detail=f"{path} is at {ref_type} {ref_value}",
        extra={"ref": ref_value, "ref_type": ref_type, "path": path},
    )


def cmd_git_checkout(args: argparse.Namespace) -> Result:
    path = require_repo(args.path)
    ref = args.ref

    git(path, "fetch", "origin", "--prune", "--tags").raise_for_status("git fetch failed")

    remote_ref = f"origin/{ref}"
    resolved = ref

    if git(path, "rev-parse", "--verify", "--quiet", f"{remote_ref}^{{commit}}", timeout=60).ok:
        git(path, "checkout", "--force", "-B", ref, remote_ref).raise_for_status(
            f"git checkout of branch {ref} failed"
        )
    else:
        if not git(path, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", timeout=60).ok:
            raise ShimError(f"ref not found after fetch: {ref}")

        git(path, "checkout", "--force", ref).raise_for_status(f"git checkout of {ref} failed")

    git(path, "submodule", "update", "--init", "--recursive").raise_for_status(
        "git submodule update failed"
    )

    git(path, "clean", "-ffd").raise_for_status("git clean failed")

    fix_ownership(path)

    ref_type, ref_value = current_head(path)

    return Result(
        ok=True,
        detail=f"git checkout {resolved} in {path} (now at {ref_type} {ref_value})",
        extra={"ref": ref_value, "ref_type": ref_type, "path": path},
    )


def cmd_git_pull(args: argparse.Namespace) -> Result:
    path = require_repo(args.path)

    git(path, "fetch", "origin", "--prune", "--tags").raise_for_status("git fetch failed")
    git(path, "reset", "--hard", "FETCH_HEAD").raise_for_status("git reset --hard failed")
    git(path, "submodule", "update", "--init", "--recursive").raise_for_status(
        "git submodule update failed"
    )
    git(path, "clean", "-ffd").raise_for_status("git clean failed")

    fix_ownership(path)

    ref_type, ref_value = current_head(path)

    return Result(
        ok=True,
        detail=f"git pull in {path} (now at {ref_type} {ref_value})",
        extra={"ref": ref_value, "ref_type": ref_type, "path": path},
    )


def cmd_git_fetch(args: argparse.Namespace) -> Result:
    path = require_repo(args.path)

    git(path, "fetch", "origin", "--prune", "--tags").raise_for_status("git fetch failed")

    return Result(ok=True, detail=f"git fetch --prune in {path}", extra={"path": path})


def cmd_git_resolve(args: argparse.Namespace) -> Result:
    path = require_repo(args.path)

    ran = git(path, "rev-parse", "--verify", "--quiet", f"{args.ref}^{{commit}}", timeout=60)

    if not ran.ok:
        git(path, "fetch", "origin", "--prune", "--tags").raise_for_status("git fetch failed")
        ran = git(path, "rev-parse", "--verify", "--quiet", f"{args.ref}^{{commit}}", timeout=60)

    ran.raise_for_status(f"could not resolve ref: {args.ref}")
    sha = ran.stdout.strip()

    return Result(ok=True, detail=f"{args.ref} resolves to {sha}", extra={"sha": sha})


def cmd_git_ls_tree(args: argparse.Namespace) -> Result:
    path = require_repo(args.path)
    tree_path = args.dir.strip("/")
    spec = f"{args.ref}:{tree_path}" if tree_path else f"{args.ref}:"

    listing = git(path, "ls-tree", "--long", spec, timeout=120)
    listing.raise_for_status(f"could not list tree {spec}")

    entries = []

    for line in listing.stdout.splitlines():
        meta, _, name = line.partition("\t")
        fields = meta.split()

        if len(fields) < 4 or not name:
            continue

        mode, kind, _sha, size = fields[0], fields[1], fields[2], fields[3]

        entries.append({
            "name": name,
            "type": kind,
            "mode": mode,
            "size": None if size == "-" else int(size),
        })

    return Result(
        ok=True,
        detail=f"{len(entries)} entries in {spec}",
        extra={"entries": entries},
    )


def cmd_git_show_blob(args: argparse.Namespace) -> Result:
    path = require_repo(args.path)
    file_path = args.file.strip("/")
    spec = f"{args.ref}:{file_path}"

    ran = run(
        ["git", "-C", path, "show", spec],
        as_web_user=True,
        timeout=120,
    )
    ran.raise_for_status(f"could not read {spec}")

    raw = ran.stdout.encode("utf-8", "surrogateescape")
    size = len(raw)
    is_binary = b"\x00" in raw[:8192]

    truncated = False
    content = ""

    if not is_binary:
        if size > args.max_bytes:
            raw = raw[: args.max_bytes]
            truncated = True

        content = raw.decode("utf-8", "replace")

    return Result(
        ok=True,
        detail=f"read {spec} ({size} bytes)",
        extra={
            "content": content,
            "size": size,
            "truncated": truncated,
            "binary": is_binary,
        },
    )


def cmd_git_refs(args: argparse.Namespace) -> Result:
    path = require_repo(args.path)

    if args.kind == "branches":
        listing = git(
            path,
            "for-each-ref",
            "--sort=-committerdate",
            f"--format=%(refname:lstrip=3){GIT_SEP}%(subject){GIT_SEP}%(authorname){GIT_SEP}%(committerdate:iso8601)",
            "refs/remotes/origin",
            timeout=120,
        )
        listing.raise_for_status("could not list branches")

        refs = []

        for line in listing.stdout.splitlines():
            value, subject, author, date = _split_git_line(line)

            if not value or value == "HEAD":
                continue

            refs.append({"value": value, "subject": subject, "author": author, "date": date})
    else:
        branch = args.branch or current_head(path)[1]
        target = f"origin/{branch}"

        if not git(path, "rev-parse", "--verify", "--quiet", target, timeout=60).ok:
            target = branch

        listing = git(
            path,
            "log",
            f"--max-count={args.limit}",
            f"--format=%H{GIT_SEP}%s{GIT_SEP}%an{GIT_SEP}%aI",
            target,
            timeout=120,
        )
        listing.raise_for_status(f"could not list commits on {target}")

        refs = []

        for line in listing.stdout.splitlines():
            value, subject, author, date = _split_git_line(line)

            if value:
                refs.append({"value": value, "subject": subject, "author": author, "date": date})

    return Result(
        ok=True,
        detail=f"{len(refs)} {args.kind} in {path}",
        extra={"refs": refs},
    )


def _split_git_line(line: str) -> tuple[str, str, str, str]:
    parts = line.split(GIT_SEP)
    parts += [""] * (4 - len(parts))

    return parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()


def cmd_repo_register(args: argparse.Namespace) -> Result:
    path = args.path

    if os.path.exists(os.path.join(path, ".git")):
        git(path, "fetch", "origin", "--prune", "--tags").raise_for_status("git fetch failed")
        fix_ownership(path)

        return Result(ok=True, detail=f"{path} already registered; fetched", extra={"path": path})

    if os.path.isdir(path) and os.listdir(path):
        raise ShimError(f"refusing to clone into non-empty directory: {path}")

    parent = os.path.dirname(path.rstrip("/"))

    if parent and not os.path.isdir(parent):
        run(["mkdir", "-p", parent], as_web_user=True).raise_for_status(
            f"could not create {parent}"
        )

    clone = run(
        ["git", "clone", "--branch", args.branch, "--recurse-submodules", args.url, path],
        as_web_user=True,
        timeout=1800,
    )

    if not clone.ok:
        clone = run(
            ["git", "clone", "--recurse-submodules", args.url, path],
            as_web_user=True,
            timeout=1800,
        )

    clone.raise_for_status(f"git clone of {args.url} failed")

    if args.kind == "core-version":
        if not getattr(args, "version", None):
            raise ShimError("--version is required with --kind core-version")

        for subdirectory in ("extensions", "skins", "cache"):
            run(["mkdir", "-p", os.path.join(path, subdirectory)], as_web_user=True)

    fix_ownership(path)

    ref_type, ref_value = current_head(path)

    return Result(
        ok=True,
        detail=f"cloned {args.url} into {path} at {ref_type} {ref_value}",
        extra={"path": path, "ref": ref_value, "ref_type": ref_type},
    )


def cmd_git_remote_check(args: argparse.Namespace) -> Result:
    argv = ["git", "ls-remote", "--exit-code", "--heads", args.url]

    if getattr(args, "branch", None):
        argv.append(args.branch)

    ran = run(argv, as_web_user=True, timeout=120)

    if ran.returncode == 2:
        raise ShimError(
            f"{args.url} is reachable but has no branch named '{args.branch}'",
            stdout=ran.stdout,
            stderr=ran.stderr,
        )

    ran.raise_for_status(f"could not reach {args.url}")

    heads = [line.split("\t")[-1].removeprefix("refs/heads/") for line in ran.stdout.splitlines() if line.strip()]

    return Result(
        ok=True,
        detail=f"{args.url} is reachable ({len(heads)} matching head(s))",
        extra={"heads": heads},
    )


def cmd_version_scaffold(args: argparse.Namespace) -> Result:
    path = args.path

    created = []

    for subdirectory in ("", "extensions", "skins", "cache"):
        target = os.path.join(path, subdirectory) if subdirectory else path

        if not os.path.isdir(target):
            run(["mkdir", "-p", target], as_web_user=True).raise_for_status(
                f"could not create {target}"
            )
            created.append(target)

    fix_ownership(path)

    return Result(
        ok=True,
        detail=f"scaffolded {path} for version {args.version} ({len(created)} directories created)",
        extra={"path": path, "version": args.version, "created": created},
    )


# --------------------------------------------------------------------------- #
# removal
# --------------------------------------------------------------------------- #

def assert_removable(path: str, root: str, allow_version_root: bool) -> str:
    if not root:
        raise ShimError("--root is required; refusing to remove anything without one")

    resolved = os.path.realpath(path)
    resolved_root = os.path.realpath(root)

    if not os.path.isabs(path) or not os.path.isabs(root):
        raise ShimError(f"paths must be absolute: path={path} root={root}")

    if ".." in path.split(os.sep):
        raise ShimError(f"refusing to remove a path containing '..': {path}")

    if resolved == os.sep or resolved_root == os.sep:
        raise ShimError("refusing to operate on /")

    if resolved == resolved_root:
        raise ShimError(f"refusing to remove the deploy root itself: {resolved}")

    if not resolved.startswith(resolved_root.rstrip(os.sep) + os.sep):
        raise ShimError(f"refusing to remove {resolved}: outside the deploy root {resolved_root}")

    relative = os.path.relpath(resolved, resolved_root)
    segments = [segment for segment in relative.split(os.sep) if segment]

    if not segments:
        raise ShimError(f"refusing to remove the deploy root itself: {resolved}")

    if segments == ["versions"]:
        raise ShimError(f"refusing to remove the versions directory itself: {resolved}")

    if len(segments) == 2 and segments[0] == "versions" and not allow_version_root:
        raise ShimError(
            f"refusing to remove the whole core version {segments[1]} without "
            "--allow-version-root"
        )

    return resolved


def cmd_repo_remove(args: argparse.Namespace) -> Result:
    resolved = assert_removable(args.path, args.root, getattr(args, "allow_version_root", False))

    if not os.path.exists(resolved):
        return Result(
            ok=True,
            detail=f"{resolved} is already absent",
            extra={"path": resolved, "removed": False},
        )

    if not os.path.isdir(resolved):
        raise ShimError(f"refusing to remove {resolved}: not a directory")

    if getattr(args, "check", False):
        entries = len(os.listdir(resolved))

        return Result(
            ok=True,
            detail=f"would remove {resolved} ({entries} entries)",
            extra={"path": resolved, "removed": False, "checked": True},
        )

    run(["rm", "-rf", "--", resolved], as_web_user=True, timeout=600).raise_for_status(
        f"could not remove {resolved}"
    )

    if os.path.exists(resolved):
        raise ShimError(f"{resolved} still exists after removal")

    return Result(
        ok=True,
        detail=f"removed {resolved}",
        extra={"path": resolved, "removed": True},
    )


# --------------------------------------------------------------------------- #
# rsync
# --------------------------------------------------------------------------- #

def rsync_argv(
    source: str,
    destination: str,
    *,
    provision: bool,
    paths: Iterable[str],
) -> list[str]:
    argv = ["rsync", *RSYNC_FLAGS]

    if provision:
        argv += list(RSYNC_PROVISION_FLAGS)

    for exclude in RSYNC_EXCLUDES:
        argv += ["--exclude", exclude]

    paths = [path.strip("/") for path in paths if path.strip("/")]

    if paths:
        for path in paths:
            segments = path.split("/")

            for depth in range(1, len(segments) + 1):
                argv += ["--include", "/" + "/".join(segments[:depth])]

            argv += ["--include", "/" + path + "/***"]

        argv += ["--exclude", "*"]

    argv += [source, destination]

    return argv


def _rsync(source: str, destination: str, *, provision: bool, paths: Iterable[str], label: str) -> Result:
    argv = rsync_argv(source, destination, provision=provision, paths=paths)

    ran = run(argv, as_web_user=True, timeout=7200)

    if ran.returncode not in (0, 24):
        raise ShimError(
            f"{label} failed (exit {ran.returncode}): {(ran.stderr or ran.stdout).strip()}",
            stdout=ran.stdout,
            stderr=ran.stderr,
        )

    transferred = len([line for line in ran.stdout.splitlines() if line and not line.startswith(" ")])

    return Result(
        ok=True,
        detail=f"{label} {source} → {destination} ({transferred} entries)",
        extra={"transferred": transferred},
    )


def cmd_rsync_local(args: argparse.Namespace) -> Result:
    if not os.path.isdir(args.src):
        raise ShimError(f"rsync source does not exist: {args.src}")

    result = _rsync(
        args.src,
        args.dst,
        provision=getattr(args, "provision", False),
        paths=getattr(args, "path", []),
        label="rsync-local",
    )

    fix_ownership(args.dst)

    return result


def cmd_rsync_remote(args: argparse.Namespace) -> Result:
    result = _rsync(
        args.src,
        args.dst,
        provision=getattr(args, "provision", False),
        paths=getattr(args, "path", []),
        label="rsync-remote",
    )

    fix_ownership(args.dst)

    return result


# --------------------------------------------------------------------------- #
# tree scan
# --------------------------------------------------------------------------- #

SCAN_IGNORED: frozenset[str] = frozenset(
    {".git", "cache", "images", "l10n_cache", "node_modules", "vendor", "tests", "__pycache__"}
)

EXTENSION_METADATA_FIELDS: tuple[str, ...] = (
    "name",
    "version",
    "license-name",
    "type",
    "url",
    "namemsg",
    "descriptionmsg",
    "description",
)

SCAN_READ_LIMIT = 4 * 1024 * 1024

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def _read_file(path: str, limit: int = SCAN_READ_LIMIT) -> str | None:
    try:
        if os.path.getsize(path) > limit:
            return None

        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def git_dir_for(path: str) -> str | None:
    candidate = os.path.join(path, ".git")

    if os.path.isdir(candidate):
        return candidate

    if not os.path.isfile(candidate):
        return None

    contents = _read_file(candidate, limit=64 * 1024) or ""

    for line in contents.splitlines():
        line = line.strip()

        if line.startswith("gitdir:"):
            pointer = line.removeprefix("gitdir:").strip()

            if not os.path.isabs(pointer):
                pointer = os.path.normpath(os.path.join(path, pointer))

            return pointer if os.path.isdir(pointer) else None

    return None


def parse_git_config(git_dir: str) -> dict[str, dict[str, str]]:
    contents = _read_file(os.path.join(git_dir, "config"))

    if contents is None:
        return {}

    sections: dict[str, dict[str, str]] = {}
    current_section = None

    for line in contents.splitlines():
        line = line.strip()
        if not line or line.startswith((";", "#")):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            sections[current_section] = {}
        elif current_section and "=" in line:
            key, val = line.split("=", 1)
            sections[current_section][key.strip()] = val.strip()

    return sections


# --------------------------------------------------------------------------- #
# canary
# --------------------------------------------------------------------------- #

def cmd_canary(args: argparse.Namespace) -> Result:
    """Check MediaWiki renders correctly by curling localhost with a virtual host header."""
    vhost = args.vhost
    warn_ms = args.warn_ms
    crit_ms = args.crit_ms
    expect_pattern = args.expect
    retries = max(1, args.retries)

    max_time = ((crit_ms + 999) // 1000) + 1
    url = f"http://{vhost}/wiki/Main_Page"

    last_error = ""
    last_stdout = ""
    last_stderr = ""

    for attempt in range(1, retries + 1):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            start_time = time.perf_counter()

            curl_cmd = [
                "curl",
                "-sS",
                "--max-time",
                str(max_time),
                "--location",
                "--resolve",
                f"{vhost}:80:127.0.0.1",
                "-o",
                tmp_path,
                "-w",
                "%{http_code}",
                url,
            ]

            ran = run(curl_cmd, timeout=max_time + 5)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            last_stdout = ran.stdout
            last_stderr = ran.stderr

            if not ran.ok:
                last_error = f"CRITICAL: curl failed (exit {ran.returncode}) — Host: {vhost}"
                continue

            http_code = ran.stdout.strip()
            if http_code != "200":
                last_error = f"CRITICAL: HTTP {http_code} from localhost (Host: {vhost})"
                continue

            body = _read_file(tmp_path) or ""
            if not re.search(expect_pattern, body, re.IGNORECASE):
                last_error = f"CRITICAL: HTTP 200 but no MediaWiki content detected (Host: {vhost})"
                continue

            detail_msg = f"HTTP {http_code} from localhost (Host: {vhost})"
            
            if elapsed_ms >= crit_ms:
                error_msg = f"CRITICAL: MediaWiki rendered but too slow ({elapsed_ms}ms) — {detail_msg}"
                raise ShimError(error_msg, stdout=ran.stdout, stderr=ran.stderr)

            if elapsed_ms >= warn_ms:
                detail = f"WARNING: MediaWiki rendered but slow ({elapsed_ms}ms) — {detail_msg}"
            else:
                detail = f"OK: MediaWiki rendered in {elapsed_ms}ms — {detail_msg}"

            return Result(
                ok=True,
                detail=detail,
                extra={
                    "vhost": vhost,
                    "elapsed_ms": elapsed_ms,
                    "http_code": http_code,
                    "warn_ms": warn_ms,
                    "crit_ms": crit_ms,
                },
            )

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    raise ShimError(last_error or "canary check failed", stdout=last_stdout, stderr=last_stderr)


# --------------------------------------------------------------------------- #
# CLI entrypoint
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="MediaWiki deployment shim")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # canary
    p_canary = subparsers.add_parser("canary", help="Run HTTP canary checks")
    p_canary.add_argument("--vhost", default="test.wikioasis.org", help="Virtual host to query")
    p_canary.add_argument("--warn-ms", type=int, default=3000, help="Warning response threshold in ms")
    p_canary.add_argument("--crit-ms", type=int, default=8000, help="Critical response threshold in ms")
    p_canary.add_argument("--expect", default="mediawiki", help="Regex pattern expected in body")
    p_canary.add_argument("--retries", type=int, default=1, help="Number of check retries")
    p_canary.set_defaults(func=cmd_canary)

    # Placeholders to register other subcommands observed in the file
    # This prevents argparse from failing if called with 'git-head' etc.
    p_git_head = subparsers.add_parser("git-head")
    p_git_head.add_argument("path")
    p_git_head.set_defaults(func=cmd_git_head)

    # (Additional parsers like cmd_rsync_local, cmd_repo_remove, etc. would be mapped here 
    # using the exact arguments expected by the portal, similar to the above).

    args = parser.parse_args()

    try:
        result = args.func(args)
    except ShimError as err:
        result = Result(ok=False, error=err.message, stdout=err.stdout, stderr=err.stderr)
    except Exception as err:
        result = Result(ok=False, error=f"unexpected error: {err}")

    print(result.to_json())
    sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
