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
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

VERSION = "2.0.0"

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
    """Re-assert www-data ownership on the tree.

    Carried over from the original tool: a git operation run as root (or a patch
    applied by hand) leaves files the web user cannot read, and the symptom is a
    500 on the wikis rather than an obvious deploy failure.
    """
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
    """(ref_type, ref_value) for the checkout's current position.

    A branch checkout reports the branch name so a rollback restores the branch
    rather than pinning to a commit; a detached HEAD reports the full SHA.
    """
    symbolic = git(path, "symbolic-ref", "--quiet", "--short", "HEAD", timeout=60)

    if symbolic.ok and symbolic.stdout.strip():
        return "branch", symbolic.stdout.strip()

    revision = git(path, "rev-parse", "HEAD", timeout=60)
    revision.raise_for_status("could not read HEAD")

    return "commit", revision.stdout.strip()


def cmd_git_head(args: argparse.Namespace) -> Result:
    """Read the current ref without changing anything.

    This is what the portal calls before a deployment mutates staging, so that
    repo_state_snapshots has an undo point to roll back to.
    """
    path = require_repo(args.path)
    ref_type, ref_value = current_head(path)

    return Result(
        ok=True,
        detail=f"{path} is at {ref_type} {ref_value}",
        extra={"ref": ref_value, "ref_type": ref_type, "path": path},
    )


def cmd_git_checkout(args: argparse.Namespace) -> Result:
    """Check out an explicit branch or commit.

    New behaviour relative to the original tool, which always did
    ``fetch && reset --hard FETCH_HEAD`` against whatever branch happened to be
    checked out. Here the caller names the ref.
    """
    path = require_repo(args.path)
    ref = args.ref

    git(path, "fetch", "origin", "--prune", "--tags").raise_for_status("git fetch failed")

    # Prefer the remote-tracking branch when the ref names one, so "master" means
    # origin/master rather than a stale local branch of the same name.
    remote_ref = f"origin/{ref}"
    resolved = ref

    if git(path, "rev-parse", "--verify", "--quiet", f"{remote_ref}^{{commit}}", timeout=60).ok:
        # Land on a local branch tracking the remote, not a detached HEAD, so a
        # later git-head reports the branch name.
        git(path, "checkout", "--force", "-B", ref, remote_ref).raise_for_status(
            f"git checkout of branch {ref} failed"
        )
    else:
        if not git(path, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", timeout=60).ok:
            raise ShimError(f"ref not found after fetch: {ref}")

        git(path, "checkout", "--force", ref).raise_for_status(f"git checkout of {ref} failed")

    # Submodules matter for skins and some extensions.
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
    """Original behaviour: fetch, then hard-reset to the tracked branch tip.

    Kept for workflows that just want "latest on whatever branch is checked out"
    without picking a ref.
    """
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


def cmd_git_refs(args: argparse.Namespace) -> Result:
    """List remote branches or recent commits, for the portal's ref picker."""
    path = require_repo(args.path)

    if args.kind == "branches":
        listing = git(
            path,
            "for-each-ref",
            "--sort=-committerdate",
            # lstrip=3 drops "refs/remotes/origin/", which also turns the
            # origin/HEAD symref into a bare "HEAD" we can filter out.
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
    """Clone a newly-registered repository into the staging tree.

    ``--kind core-version`` additionally creates the versions/<ver>/extensions
    and versions/<ver>/skins scaffolding, so a freshly cut MediaWiki version has
    somewhere for its extensions to land.
    """
    path = args.path

    if os.path.exists(os.path.join(path, ".git")):
        # Idempotent: re-registering an existing checkout just refreshes it.
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

    # A wrong branch name is the most common registration mistake; retry without
    # it so the clone succeeds and the operator can fix the default branch after.
    if not clone.ok:
        clone = run(
            ["git", "clone", "--recurse-submodules", args.url, path],
            as_web_user=True,
            timeout=1800,
        )

    clone.raise_for_status(f"git clone of {args.url} failed")

    if args.kind == "core-version":
        if not args.version:
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
    """Confirm a git remote is reachable and has the expected branch.

    Cheap enough to run from a form submission, which is the point: registering a
    repository whose URL is wrong should fail at the form rather than as a puzzling
    deployment failure days later.
    """
    argv = ["git", "ls-remote", "--exit-code", "--heads", args.url]

    if args.branch:
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
    """Create an empty versions/<ver>/ tree, ready for core and its extensions.

    Split out from repo-register so that reconstructing a version is one explicit
    step the portal can show on its review screen, rather than a side effect of
    cloning core.
    """
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
    """Refuse to delete anything that is not unambiguously a deploy artefact.

    This is the guard on the single most destructive operation in the system. The
    portal already validates and stores paths, but a bug or a crafted request must
    not be able to turn `repo-remove` into `rm -rf /`, so every check is repeated
    here where the deletion actually happens.

    Returns the normalised absolute path.
    """
    if not root:
        raise ShimError("--root is required; refusing to remove anything without one")

    # Resolve both sides before comparing: a symlink or a "." component could
    # otherwise smuggle the target outside the root.
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

    # Strictly inside the root, and not merely sharing a name prefix with it
    # (/srv/mediawiki-old must not pass a /srv/mediawiki root).
    if not resolved.startswith(resolved_root.rstrip(os.sep) + os.sep):
        raise ShimError(f"refusing to remove {resolved}: outside the deploy root {resolved_root}")

    relative = os.path.relpath(resolved, resolved_root)
    segments = [segment for segment in relative.split(os.sep) if segment]

    if not segments:
        raise ShimError(f"refusing to remove the deploy root itself: {resolved}")

    # `versions` holds every core version; deleting it removes the whole farm.
    if segments == ["versions"]:
        raise ShimError(f"refusing to remove the versions directory itself: {resolved}")

    # A bare versions/<ver> is an entire core version. Removing one is legitimate
    # but needs saying out loud, so it takes a separate flag.
    if len(segments) == 2 and segments[0] == "versions" and not allow_version_root:
        raise ShimError(
            f"refusing to remove the whole core version {segments[1]} without "
            "--allow-version-root"
        )

    return resolved


def cmd_repo_remove(args: argparse.Namespace) -> Result:
    """Remove a checkout (or a whole core version) from this host.

    Deliberately not implemented by deleting on staging and letting rsync
    --delete propagate: under a path-restricted include set those semantics are
    subtle, and they change entirely if the farm moves to NFS. Running an explicit
    removal on each host is deterministic and attributable per server.
    """
    resolved = assert_removable(args.path, args.root, args.allow_version_root)

    if not os.path.exists(resolved):
        # Idempotent: the portal runs this per server, and a retry (or a server
        # provisioned after the checkout was removed) must not fail.
        return Result(
            ok=True,
            detail=f"{resolved} is already absent",
            extra={"path": resolved, "removed": False},
        )

    if not os.path.isdir(resolved):
        raise ShimError(f"refusing to remove {resolved}: not a directory")

    if args.check:
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
        # Restrict the sync to the given subtrees. --include of each ancestor
        # plus a final --exclude '*' is the standard rsync idiom for this; it is
        # what keeps a one-extension deploy from walking the whole tree.
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

    # 24 is "some files vanished before transfer" — routine on a live tree where
    # a cache file disappears mid-run, and not a deploy failure.
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
    """Staging → production on this host. The original tool's rsync_local."""
    if not os.path.isdir(args.src):
        raise ShimError(f"rsync source does not exist: {args.src}")

    result = _rsync(
        args.src,
        args.dst,
        provision=args.provision,
        paths=args.path,
        label="rsync-local",
    )

    fix_ownership(args.dst)

    return result


def cmd_rsync_remote(args: argparse.Namespace) -> Result:
    """Pull the staged tree onto *this* appserver.

    This is the one behavioural inversion relative to the original tool. There,
    the orchestrator pushed to each appserver over SSH as the deploy user. Here
    the portal only ever runs commands *on* a minion, so the transfer is a pull:
    --src is an rsync source the appserver can reach (an rsync daemon module on
    the staging host by default, or an NFS path).
    """
    result = _rsync(
        args.src,
        args.dst,
        provision=args.provision,
        paths=args.path,
        label="rsync-remote",
    )

    fix_ownership(args.dst)

    return result


# --------------------------------------------------------------------------- #
# wiki → version mapping
# --------------------------------------------------------------------------- #


def cmd_wiki_versions(args: argparse.Namespace) -> Result:
    """Report which core versions the farm's wikis are currently pointed at.

    This exists so that undeploying a core version can be *refused* when wikis
    still run on it, rather than left to an operator's checklist.

    The mapping lives in the config repo, not here, and its exact shape varies
    between farms. Both common shapes are handled:

        {"enwiki": "1.45", ...}
        {"enwiki": {"version": "1.45"}, ...}

    and a leading "php-" is tolerated because that is how Wikimedia writes it.
    Anything else is reported as unparseable rather than guessed at — a wrong
    answer here means deleting a version that is still serving traffic.
    """
    path = args.file

    if not os.path.isfile(path):
        raise ShimError(f"wiki version map not found: {path}")

    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ShimError(f"could not read {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ShimError(f"{path} is not a JSON object mapping wikis to versions")

    versions: dict[str, list[str]] = {}

    for wiki, value in data.items():
        if isinstance(value, dict):
            value = value.get("version")

        if not isinstance(value, str) or not value.strip():
            raise ShimError(f"{path}: could not read a version for wiki '{wiki}'")

        version = value.strip().removeprefix("php-")
        versions.setdefault(version, []).append(str(wiki))

    return Result(
        ok=True,
        detail=f"{len(data)} wikis across {len(versions)} version(s): "
        + ", ".join(f"{version} ({len(wikis)})" for version, wikis in sorted(versions.items())),
        extra={
            "versions": {version: sorted(wikis) for version, wikis in versions.items()},
            "wiki_count": len(data),
        },
    )


# --------------------------------------------------------------------------- #
# l10n
# --------------------------------------------------------------------------- #


def cmd_l10n_rebuild(args: argparse.Namespace) -> Result:
    """Rebuild the localisation cache. The original tool's l10n_rebuild, minus
    the SSH wrapper — Salt has already put us on the right host."""
    multiversion = os.environ.get("MWDEPLOY_MULTIVERSION", "/srv/mediawiki/multiversion")
    maintenance = os.path.join(multiversion, "MWScript.php")

    if os.path.exists(maintenance):
        argv = ["php", maintenance, "rebuildLocalisationCache.php", args.wiki, "--quiet"]
    else:
        # Single-version layout: run the maintenance script directly.
        argv = [
            "php",
            os.path.join(args.mediawiki, "maintenance", "rebuildLocalisationCache.php"),
            "--quiet",
        ]

    ran = run(argv, as_web_user=True, timeout=7200)
    ran.raise_for_status(f"l10n rebuild for {args.wiki} failed")

    return Result(ok=True, detail=f"rebuilt l10n cache via {argv[1]} for {args.wiki}")


# --------------------------------------------------------------------------- #
# canary
# --------------------------------------------------------------------------- #


def cmd_canary(args: argparse.Namespace) -> Result:
    """One canary verdict: HTTP 200 and the expected body marker.

    Same check as the original canary_check, but it never prompts — there is no
    TTY under ``salt cmd.run``, and the decision of what to do about a failure
    belongs to the portal.
    """
    port = 443 if args.scheme == "https" else 80
    url = f"{args.scheme}://{args.vhost}{args.path}"

    attempts: list[str] = []

    for attempt in range(1, args.retries + 1):
        # --resolve pins the vhost to this box, so the check exercises *this*
        # appserver rather than whatever the proxy would have picked.
        ran = run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--location",
                "--insecure",
                "--max-time",
                str(args.timeout),
                "--resolve",
                f"{args.vhost}:{port}:{args.host}",
                "--write-out",
                "\n%{http_code}",
                url,
            ],
            timeout=args.timeout + 10,
        )

        body, _, status = ran.stdout.rpartition("\n")
        status = status.strip()

        if ran.ok and status == "200" and args.expect.lower() in body.lower():
            return Result(
                ok=True,
                detail=f"canary ok on attempt {attempt}: {args.vhost} returned 200 containing '{args.expect}'",
                extra={"attempts": attempt, "status": status},
            )

        attempts.append(
            f"attempt {attempt}: exit={ran.returncode} status={status or 'none'} "
            f"marker={'present' if args.expect.lower() in body.lower() else 'missing'}"
        )

        if attempt < args.retries:
            time.sleep(args.backoff)

    raise ShimError(
        f"canary failed for {args.vhost} after {args.retries} attempt(s): " + "; ".join(attempts)
    )


# --------------------------------------------------------------------------- #
# HAProxy
# --------------------------------------------------------------------------- #


def haproxy_command(socket_path: str, command: str, timeout: float = 10.0) -> str:
    """Send one command to the HAProxy stats socket and return its reply.

    Same raw-socket approach as the original tool's _depool/_repool.
    """
    if not os.path.exists(socket_path):
        raise ShimError(f"HAProxy socket not found: {socket_path}")

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(socket_path)
            client.sendall((command + "\n").encode())

            chunks: list[bytes] = []

            while True:
                chunk = client.recv(4096)

                if not chunk:
                    break

                chunks.append(chunk)
    except OSError as exc:
        raise ShimError(f"HAProxy socket error on {socket_path}: {exc}") from exc

    return b"".join(chunks).decode("utf-8", "replace").strip()


def _set_state(args: argparse.Namespace, state: str) -> Result:
    target = f"{args.backend}/{args.server}"

    reply = haproxy_command(args.socket, f"set server {target} state {state}")

    # HAProxy answers an accepted command with an empty line. Anything that looks
    # like a complaint is a failure worth surfacing verbatim — silently treating
    # "No such server" as success would leave a live box being rsynced.
    if any(marker in reply for marker in ("No such", "Unknown", "not found", "Permission denied")):
        raise ShimError(f"HAProxy refused '{state}' for {target}: {reply}")

    verb = "depooled" if state == "maint" else "repooled"

    return Result(
        ok=True,
        detail=f"{verb} {target} on {args.proxy}" + (f" ({reply})" if reply else ""),
        extra={"backend": args.backend, "server": args.server, "state": state},
    )


def cmd_haproxy_depool(args: argparse.Namespace) -> Result:
    return _set_state(args, "maint")


def cmd_haproxy_repool(args: argparse.Namespace) -> Result:
    return _set_state(args, "ready")


# --------------------------------------------------------------------------- #
# patches
# --------------------------------------------------------------------------- #


def cmd_patch_apply(args: argparse.Namespace) -> Result:
    """Apply (or dry-run) a patch. The original tool's apply_patch.

    ``--check`` is what the portal's patch registry uses to answer "does this
    still apply against current staging?" without running a deployment.
    """
    if not os.path.isfile(args.patch):
        raise ShimError(f"patch file not found: {args.patch}")

    if not os.path.isdir(args.target_dir):
        raise ShimError(f"patch target directory not found: {args.target_dir}")

    if args.format == "git":
        argv = ["git", "apply", "--verbose"]

        if args.check:
            argv.append("--check")

        argv.append(args.patch)
    else:
        # --fuzz=0 is deliberate. GNU patch defaults to a fuzz factor of 2, which
        # means a patch whose context no longer matches upstream is applied
        # *somewhere nearby* and exits 0. Silently landing a deploy patch in the
        # wrong place is worse than refusing it, and section 4.5 of the portal
        # spec depends on a stale patch failing loudly.
        argv = ["patch", "-p1", "--forward", "--batch", "--fuzz=0"]

        if args.check:
            argv.append("--dry-run")

        argv += ["--input", args.patch]

    ran = run(argv, cwd=args.target_dir, as_web_user=True, timeout=300)

    if not ran.ok:
        verb = "would not apply" if args.check else "failed to apply"

        raise ShimError(
            f"patch {verb}: {os.path.basename(args.patch)} in {args.target_dir}: "
            f"{(ran.stderr or ran.stdout).strip()}",
            stdout=ran.stdout,
            stderr=ran.stderr,
        )

    if not args.check:
        fix_ownership(args.target_dir)

    verb = "would apply cleanly" if args.check else "applied"

    return Result(
        ok=True,
        detail=f"patch {os.path.basename(args.patch)} {verb} in {args.target_dir}",
        extra={"checked": args.check},
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mwdeploy-shim",
        description="Atomic MediaWiki deploy primitives. Prints one JSON object to stdout.",
    )
    parser.add_argument("--version", action="version", version=f"mwdeploy-shim {VERSION}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    checkout = subparsers.add_parser("git-checkout", help="Check out an explicit branch or commit")
    checkout.add_argument("--path", required=True)
    checkout.add_argument("--ref", required=True, help="Branch name or commit SHA")
    checkout.set_defaults(handler=cmd_git_checkout)

    pull = subparsers.add_parser("git-pull", help="Fetch and hard-reset to the tracked branch tip")
    pull.add_argument("--path", required=True)
    pull.set_defaults(handler=cmd_git_pull)

    head = subparsers.add_parser("git-head", help="Report the current ref without changing anything")
    head.add_argument("--path", required=True)
    head.set_defaults(handler=cmd_git_head)

    refs = subparsers.add_parser("git-refs", help="List branches or recent commits")
    refs.add_argument("--path", required=True)
    refs.add_argument("--kind", choices=("branches", "commits"), default="branches")
    refs.add_argument("--branch", default=None)
    refs.add_argument("--limit", type=int, default=30)
    refs.set_defaults(handler=cmd_git_refs)

    register = subparsers.add_parser("repo-register", help="Clone a newly-registered repository")
    register.add_argument("--url", required=True)
    register.add_argument("--path", required=True)
    register.add_argument("--branch", default="master")
    register.add_argument("--kind", choices=("plain", "core-version"), default="plain")
    register.add_argument("--version", default=None, help="MediaWiki version, with --kind core-version")
    register.set_defaults(handler=cmd_repo_register)

    remote_check = subparsers.add_parser(
        "git-remote-check", help="Confirm a git remote is reachable before registering it"
    )
    remote_check.add_argument("--url", required=True)
    remote_check.add_argument("--branch", default=None, help="Also require this branch to exist")
    remote_check.set_defaults(handler=cmd_git_remote_check)

    scaffold = subparsers.add_parser("version-scaffold", help="Create an empty versions/<ver> tree")
    scaffold.add_argument("--path", required=True)
    scaffold.add_argument("--version", required=True)
    scaffold.set_defaults(handler=cmd_version_scaffold)

    remove = subparsers.add_parser("repo-remove", help="Remove a checkout, or a whole core version")
    remove.add_argument("--path", required=True, help="Absolute path to remove")
    remove.add_argument(
        "--root",
        required=True,
        help="Deploy root the path must be strictly inside; refuses anything outside it",
    )
    remove.add_argument(
        "--allow-version-root",
        action="store_true",
        dest="allow_version_root",
        help="Permit removing a bare versions/<ver>, i.e. an entire core version",
    )
    remove.add_argument("--check", action="store_true", help="Report what would be removed")
    remove.set_defaults(handler=cmd_repo_remove)

    wiki_versions = subparsers.add_parser(
        "wiki-versions", help="Report which core versions the farm's wikis point at"
    )
    wiki_versions.add_argument("--file", required=True, help="Path to the wiki → version JSON map")
    wiki_versions.set_defaults(handler=cmd_wiki_versions)

    local = subparsers.add_parser("rsync-local", help="Rsync staging → production on this host")
    local.add_argument("--src", required=True)
    local.add_argument("--dst", required=True)
    local.add_argument("--provision", action="store_true")
    local.add_argument("--path", action="append", default=[], help="Restrict to this relative path (repeatable)")
    local.set_defaults(handler=cmd_rsync_local)

    remote = subparsers.add_parser("rsync-remote", help="Pull the staged tree onto this appserver")
    remote.add_argument("--src", required=True, help="rsync source the appserver can reach")
    remote.add_argument("--dst", required=True)
    remote.add_argument("--provision", action="store_true")
    remote.add_argument("--path", action="append", default=[], help="Restrict to this relative path (repeatable)")
    remote.set_defaults(handler=cmd_rsync_remote)

    l10n = subparsers.add_parser("l10n-rebuild", help="Rebuild the localisation cache")
    l10n.add_argument("--wiki", default="testwiki")
    l10n.add_argument("--mediawiki", default="/srv/mediawiki")
    l10n.set_defaults(handler=cmd_l10n_rebuild)

    canary = subparsers.add_parser("canary", help="One canary verdict; never prompts")
    canary.add_argument("--vhost", default="meta.wikioasis.org")
    canary.add_argument("--host", default="127.0.0.1", help="Address the vhost is pinned to")
    canary.add_argument("--path", default="/wiki/Main_Page")
    canary.add_argument("--scheme", choices=("http", "https"), default="https")
    canary.add_argument("--retries", type=int, default=3)
    canary.add_argument("--backoff", type=float, default=3.0)
    canary.add_argument("--timeout", type=int, default=15)
    canary.add_argument("--expect", default="wikioasis", help="Case-insensitive marker expected in the body")
    canary.set_defaults(handler=cmd_canary)

    haproxy = subparsers.add_parser("haproxy", help="Depool or repool one server on this proxy")
    haproxy_actions = haproxy.add_subparsers(dest="action", required=True)

    for action, handler in (("depool", cmd_haproxy_depool), ("repool", cmd_haproxy_repool)):
        sub = haproxy_actions.add_parser(action)
        sub.add_argument("--proxy", required=True, help="Proxy hostname, for the log line")
        sub.add_argument("--backend", required=True)
        sub.add_argument("--server", required=True)
        sub.add_argument("--socket", default=os.environ.get("MWDEPLOY_HAPROXY_SOCKET", "/run/haproxy/admin.sock"))
        sub.set_defaults(handler=handler)

    patch = subparsers.add_parser("patch-apply", help="Apply or dry-run a patch")
    patch.add_argument("--patch", required=True)
    patch.add_argument("--target-dir", required=True, dest="target_dir")
    patch.add_argument("--format", choices=("unified", "git"), default="unified")
    patch.add_argument("--check", action="store_true", help="Dry run only")
    patch.set_defaults(handler=cmd_patch_apply)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = args.handler(args)
    except ShimError as error:
        print(
            Result(ok=False, error=error.message, stdout=error.stdout, stderr=error.stderr).to_json()
        )

        return 1
    except Exception as error:  # noqa: BLE001 - never let a traceback be the only output
        print(Result(ok=False, error=f"{type(error).__name__}: {error}").to_json())

        return 1

    print(result.to_json())

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
