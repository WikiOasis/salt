#!/usr/bin/env python3
"""Fandom import worker for the WikiOasis wiki farm.

Special:FandomImport on the central wiki (extension WikiOasisMagic) creates the
target wiki, then a MediaWiki job on this host drops a manifest into the
spool's queue/ directory. This worker, run every minute by cron as www-data,
picks the manifests up and does the long-running part entirely outside
MediaWiki:

  resolve   fetch the Fandom wiki's siteinfo
  prepare   FandomImportPrepare: namespaces and extensions on the target wiki
  dump      find a usable Fandom XML dump on S3 and download it
  pages     drop unwanted namespaces, importDump, rebuild RC and site stats
  images    list the source wiki's files and download them with wikiteam3
  upload    importImages whatever wikiteam3 downloaded
  finalize  initSiteStats, report `done`, delete every working file

and reports back by running the FandomImportCallback maintenance script on the
central wiki.

Spool layout (<spool_dir>, owned by www-data):

  queue/<id>.json     written by MediaWiki: "run or resume import <id>"
  queue/<id>.discard  written by MediaWiki: "delete all working files of <id>"
  work/<id>/          worker-owned: manifest.json, state.json, downloads, tmp/
  logs/<id>.log       per-import log (logs/worker.log is cron's output)
  tmp/                TMPDIR for subprocesses that belong to no import
  worker.lock         flock()ed by whichever run is active

Every stage is idempotent and the state is persisted after each step, so a
crash or reboot resumes where it stopped. Only one import runs at a time. A
long one holds the lock for hours or days, so it does the cheap housekeeping
for the others (discards, expiries, callback retries) from its poll loops.

Disk space is the scarce resource: the dump is deleted as soon as the filtered
XML exists, the XML as soon as it is imported, and each image directory as
soon as importImages is done with it. Failed imports keep their files for
`failed_retention_days` so a retry can resume, then they are deleted too.

All HTTP goes through the squid proxy on the metal host: this VM has IPv6-only
egress and neither Fandom nor S3 publish AAAA records.

Notes on the constants below:

  * STAGES are shown verbatim by the MediaWiki UI.
  * Tombstone statuses (done, deleted, rejected) mean everything but
    state.json/manifest.json is gone; the work dir survives only until its
    terminal callbacks are delivered.
  * TERMINAL_EVENTS are the callbacks MediaWiki must not miss: they are
    persisted in state.json and retried. `progress` is sent at most once per
    PROGRESS_INTERVAL per import.
  * GZIP_RATIO_ESTIMATE is a pessimistic XML-to-gzip ratio, used to decide
    whether the filtered XML will fit before starting to write it.
  * Fandom moves dumps older than about a year to cold storage: HEAD still
    says 200, but GET fails with 403 InvalidObjectState unless a restored copy
    exists (UNUSABLE_STORAGE_CLASSES).
  * Validation uses re.fullmatch(), because `$` also matches before a
    trailing newline.

Python 3.11+, standard library only. It is started from the wikiteam3 venv
but must not depend on anything installed there.
"""

from __future__ import annotations

import argparse
import email.utils
import errno
import fcntl
import gzip
import hashlib
import http.client
import io
import json
import logging
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Collection, Iterable, Mapping, Optional, Sequence

LOG = logging.getLogger("fandom_import")

GiB = 1024 ** 3

STAGES: tuple[str, ...] = ("resolve", "prepare", "dump", "pages", "images", "upload", "finalize")

STATUS_RUNNING = "running"
STATUS_WAITING_DUMP = "waiting-dump"
STATUS_FAILED = "failed"
STATUS_DONE = "done"
STATUS_DELETED = "deleted"
STATUS_REJECTED = "rejected"
TOMBSTONE_STATUSES = frozenset({STATUS_DONE, STATUS_DELETED, STATUS_REJECTED})
KNOWN_STATUSES = frozenset({STATUS_RUNNING, STATUS_WAITING_DUMP, STATUS_FAILED}) | TOMBSTONE_STATUSES

TERMINAL_EVENTS = frozenset({"done", "failed", "waiting-dump", "files-deleted"})

PROGRESS_INTERVAL = 5 * 60
CALLBACK_TIMEOUT = 300
CALLBACK_BACKOFF_MAX = 60 * 60
STAGE_BACKOFF = (15 * 60, 60 * 60, 4 * 60 * 60)
DISK_RETRY = 60 * 60
POLL_INTERVAL = 30
HOUSEKEEPING_INTERVAL = 5 * 60
ORPHAN_AGE = 24 * 60 * 60
STRAY_AGE = 24 * 60 * 60
MAX_INTERRUPTIONS = 10
FAILED_FILES_KEEP = 100
API_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 60
DOWNLOAD_CHUNK = 1024 * 1024
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_TOOL_LINE = 1024 * 1024
GZIP_LEVEL = 6
GZIP_RATIO_ESTIMATE = 4
WIKITEAM3_CHUNKSIZE = 500

UNUSABLE_STORAGE_CLASSES = frozenset({"GLACIER", "DEEP_ARCHIVE"})
DUMP_URL = "https://s3.amazonaws.com/wikia_xml_dumps/{first}/{first2}/{wikiid}_pages_{variant}.xml.7z"

DUMP_FILE = "dump.xml.7z"
PAGES_FILE = "pages.xml.gz"
CRAWL_DIR = "crawl"
IMAGE_DIRS = ("images", "images_mismatch")
TOMBSTONE_KEEP = frozenset({"state.json", "manifest.json"})

CHILD_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

DBNAME_RE = re.compile(r"[a-z0-9_]{1,64}")
SUBDOMAIN_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
LANG_RE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{1,8})*")
USERNAME_PREFIX_RE = re.compile(r"[a-z0-9]{1,16}")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
USER_NAME_FORBIDDEN_RE = re.compile(r"[#<>\[\]|{}/:]")
ID_RE = re.compile(r"[1-9][0-9]{0,17}")
QUEUE_MANIFEST_RE = re.compile(r"([1-9][0-9]{0,17})\.json")
QUEUE_DISCARD_RE = re.compile(r"([1-9][0-9]{0,17})\.discard")
IMPORT_LOG_RE = re.compile(r"[1-9][0-9]{0,17}\.log")
MD5_RE = re.compile(r"[0-9a-f]{32}")
NS_LINE_RE = re.compile(r"\s*<ns>(-?[0-9]+)</ns>\s*")
IMPORTDUMP_REPORT_RE = re.compile(r"([0-9]+) \([0-9.]+ pages/sec")
IMPORTIMAGES_SUMMARY_RE = re.compile(r"(Found|Limit|Ignored|Added|Skipped|Overwritten|Failed): ([0-9]+)")
IMPORTIMAGES_LINE_RE = re.compile(
    r"Importing (?P<name>.+)\.\.\.(?P<outcome>done\.|failed\. \((?P<reason>.*)\)|skipped\. \(.*\))?"
)


class StageError(Exception):
    """A stage failed. Counts against max_stage_attempts unless `permanent`."""

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


class ManifestError(ValueError):
    """An unusable manifest. Carries whatever could be trusted for reporting."""

    def __init__(self, message: str, import_id: Optional[int] = None,
                 central_wiki: Optional[str] = None) -> None:
        super().__init__(message)
        self.import_id = import_id
        self.central_wiki = central_wiki


class UnsafePathError(RuntimeError):
    """safe_rmtree() refused to delete something."""


class DumpFormatError(ValueError):
    """The XML dump does not look like a MediaWiki export."""


class LowDiskSpace(Exception):
    """Raised from inside a long write when free space drops below the floor."""


class WorkerInterrupted(BaseException):
    """SIGTERM/SIGINT. A BaseException so no `except Exception` swallows it."""


@dataclass
class Deferral:
    """Stop for now and come back later without counting a failed attempt."""
    seconds: int
    message: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Rewind:
    """Something an earlier stage produced is gone: run that stage again."""
    stage: str
    reason: str


WAITING = "waiting"
FINISHED = "finished"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_int(value: Any) -> bool:
    """True for real integers. bool is an int subclass; JSON `true` is not 1."""
    return isinstance(value, int) and not isinstance(value, bool)


def clean_text(value: Any, limit: int) -> str:
    """One line of printable text, for callback messages and log lines."""
    text = CONTROL_CHARS_RE.sub(" ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{n} B"


def read_json_file(path: Path, limit: int) -> Any:
    with open(path, "rb") as f:
        raw = f.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"{path.name} is larger than {limit} bytes")
    return json.loads(raw.decode("utf-8"))


def write_json_atomic(path: Path, data: Any) -> None:
    """Write-then-rename, so a crash leaves either the old or the new file."""
    tmp = path.with_name(f".tmp-{path.name}.{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def tree_size(path: Path) -> int:
    """Bytes used by regular files under `path`, without following symlinks."""
    total = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                st = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                total += st.st_size
    return total


def count_files(path: Path) -> int:
    """Regular files under `path` (recursively); 0 if it does not exist."""
    count = 0
    stack = [str(path)]
    while stack:
        current = stack.pop()
        try:
            it = os.scandir(current)
        except (FileNotFoundError, NotADirectoryError):
            continue
        with it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    count += 1
    return count


def _strictly_inside(real: str, root: Path) -> bool:
    """Whether `real` lies below (never at) root's real path. A root that
    resolves to / is refused, since "inside" would then mean everything."""
    root_real = os.path.realpath(root)
    if root_real == os.sep:
        return False
    return real != root_real and real.startswith(root_real.rstrip(os.sep) + os.sep)


def safe_rmtree(path: Path, roots: Iterable[Path],
                log: Optional[Callable[[str], None]] = None) -> int:
    """The only way this worker deletes anything. Returns the bytes freed.

    Refuses symlinks outright and anything whose real path is not strictly
    inside one of `roots`. Directories go through shutil.rmtree (which does not
    follow symlinks inside the tree), files through os.unlink. Missing paths
    are not an error: deletion is often a retry of an interrupted one.
    """
    path = Path(os.path.abspath(path))
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return 0
    if stat.S_ISLNK(st.st_mode):
        raise UnsafePathError(f"refusing to delete symlink {path}")
    real = os.path.realpath(path)
    if not any(_strictly_inside(real, root) for root in roots):
        raise UnsafePathError(f"refusing to delete {path}: not inside {', '.join(map(str, roots))}")
    if stat.S_ISDIR(st.st_mode):
        freed = tree_size(Path(real))
        shutil.rmtree(real)
    else:
        freed = st.st_size
        os.unlink(real)
    (log or LOG.info)(f"deleted {path} ({human_bytes(freed)} freed)")
    return freed


def source_urls(subdomain: str, lang: Optional[str]) -> tuple[str, str]:
    """(base_url, api_url) rebuilt from the parts; never taken from the file."""
    base = f"https://{subdomain}.fandom.com" + (f"/{lang}" if lang else "")
    return base, base + "/api.php"


def validate_user_name(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 85:
        raise ValueError("user name must be 1-85 characters")
    if CONTROL_CHARS_RE.search(value) or USER_NAME_FORBIDDEN_RE.search(value):
        raise ValueError("user name contains a forbidden character")
    return value


@dataclass(frozen=True)
class Source:
    key: str
    subdomain: str
    lang: Optional[str]
    base_url: str
    api_url: str

    @property
    def index_url(self) -> str:
        return self.base_url + "/index.php"


@dataclass(frozen=True)
class Manifest:
    id: int
    central_wiki: str
    target_wiki: str
    source: Source
    username_prefix: str
    upload_user: str
    summary: str
    prefer_full_history: Optional[bool]


def validate_manifest(data: Any, *, expected_id: Optional[int] = None,
                      central_wiki: Optional[str] = None) -> Manifest:
    """Check every field of a v1 manifest. Raises ManifestError.

    The error carries the id and central wiki only when both can be trusted,
    so the caller knows whether a `failed` callback can be sent. An id that
    does not match the file name trusts neither number, so nothing is
    reported anywhere.
    """
    if not isinstance(data, dict):
        raise ManifestError("manifest is not a JSON object")

    raw_id = data.get("id")
    import_id = raw_id if is_int(raw_id) and 0 < raw_id < 10 ** 18 else None
    if expected_id is not None and import_id != expected_id:
        raise ManifestError(f"manifest id {raw_id!r} does not match its file name ({expected_id})")
    raw_central = data.get("central_wiki")
    central_ok = (isinstance(raw_central, str) and DBNAME_RE.fullmatch(raw_central) is not None
                  and (central_wiki is None or raw_central == central_wiki))
    known_central = raw_central if central_ok else None

    def bad(message: str) -> ManifestError:
        return ManifestError(message, import_id, known_central)

    if not is_int(data.get("version")) or data["version"] != 1:
        raise bad("unsupported manifest version")
    if import_id is None:
        raise bad("id must be a positive integer")
    if not central_ok:
        raise bad("central_wiki is invalid or not this farm's central wiki")

    target = data.get("target_wiki")
    if not isinstance(target, str) or not DBNAME_RE.fullmatch(target):
        raise bad("target_wiki is invalid")
    if target == raw_central:
        raise bad("target_wiki must not be the central wiki")

    source = data.get("source")
    if not isinstance(source, dict):
        raise bad("source must be an object")
    subdomain = source.get("subdomain")
    if not isinstance(subdomain, str) or not SUBDOMAIN_RE.fullmatch(subdomain):
        raise bad("source.subdomain is invalid")
    lang = source.get("lang")
    if lang is not None and (not isinstance(lang, str) or len(lang) > 35 or not LANG_RE.fullmatch(lang)):
        raise bad("source.lang is invalid")
    expected_key = subdomain if lang is None else f"{subdomain}/{lang}"
    if source.get("key") != expected_key:
        raise bad("source.key does not match subdomain/lang")
    base_url, api_url = source_urls(subdomain, lang)
    if source.get("base_url") != base_url or source.get("api_url") != api_url:
        raise bad("source.base_url/api_url do not match subdomain/lang")

    prefix = data.get("username_prefix")
    if not isinstance(prefix, str) or not USERNAME_PREFIX_RE.fullmatch(prefix):
        raise bad("username_prefix is invalid")
    try:
        upload_user = validate_user_name(data.get("upload_user"))
    except ValueError as e:
        raise bad(f"upload_user: {e}") from None
    summary = data.get("summary")
    if not isinstance(summary, str) or len(summary) > 500 or CONTROL_CHARS_RE.search(summary):
        raise bad("summary must be at most 500 characters without control characters")

    prefer = data.get("prefer_full_history")
    if prefer is not None and not isinstance(prefer, bool):
        raise bad("prefer_full_history must be a boolean")
    queued_at = data.get("queued_at")
    if queued_at is not None and (not isinstance(queued_at, str) or len(queued_at) > 64):
        raise bad("queued_at is invalid")
    attempt = data.get("attempt")
    if attempt is not None and (not is_int(attempt) or attempt < 1):
        raise bad("attempt is invalid")

    return Manifest(
        id=import_id,
        central_wiki=raw_central,
        target_wiki=target,
        source=Source(key=expected_key, subdomain=subdomain, lang=lang,
                      base_url=base_url, api_url=api_url),
        username_prefix=prefix,
        upload_user=upload_user,
        summary=summary,
        prefer_full_history=prefer,
    )


def validate_discard(data: Any, expected_id: int, central_wiki: str) -> None:
    if not isinstance(data, dict):
        raise ValueError("discard request is not a JSON object")
    if not is_int(data.get("version")) or data["version"] != 1:
        raise ValueError("unsupported discard version")
    if data.get("id") != expected_id or not is_int(data.get("id")):
        raise ValueError("discard id does not match its file name")
    if data.get("central_wiki") != central_wiki:
        raise ValueError("discard is not from this farm's central wiki")


def dump_candidates(wikiid: str, prefer_full_history: bool) -> list[tuple[str, str]]:
    """[(variant, url), ...] in the order they should be tried."""
    if not DBNAME_RE.fullmatch(wikiid):
        raise ValueError(f"invalid Fandom wiki id {wikiid!r}")
    variants = ("full", "current") if prefer_full_history else ("current", "full")
    return [(v, DUMP_URL.format(first=wikiid[0], first2=wikiid[:2], wikiid=wikiid, variant=v))
            for v in variants]


@dataclass
class FilterStats:
    pages_kept: int = 0
    pages_skipped: int = 0
    skipped_namespaces: dict[str, int] = field(default_factory=dict)
    saw_footer: bool = False


_PAGE_OPEN = "<page>"
_PAGE_CLOSE = "</page>"
_FOOTER = "</mediawiki>"
_STRUCTURAL_MAX = 64
_MAX_PAGE_HEADER_LINES = 1000


def filter_dump_lines(lines: Iterable[str], write: Callable[[str], Any], keep: Collection[int],
                      check: Optional[Callable[[], None]] = None,
                      check_every: int = 10000) -> FilterStats:
    """Copy a MediaWiki XML export, dropping <page>s outside `keep`.

    Export XML puts <page>, <ns> and </page> on lines of their own, and page
    text cannot contain a raw "<" (it is escaped as &lt;), so whole-line
    matching is safe. Lines between <page> and <ns> are buffered until the
    namespace is known; everything outside pages (header, <siteinfo>, the
    closing </mediawiki>) is copied unchanged. Only short lines are strip()ped
    and compared, which keeps multi-kilobyte text lines cheap. A <page>
    without <ns> (pre-0.6 export schema) is kept, and MediaWiki works the
    namespace out from the title. `check` is called every `check_every`
    lines (the disk-space guard).
    """
    stats = FilterStats()
    outside, header, keeping, dropping = range(4)
    mode = outside
    buffered: list[str] = []
    count = 0
    for line in lines:
        count += 1
        if check is not None and count % check_every == 0:
            check()
        short = line.strip() if len(line) <= _STRUCTURAL_MAX else None
        if mode == outside:
            if short == _PAGE_OPEN:
                mode = header
                buffered = [line]
                continue
            if short == _FOOTER:
                stats.saw_footer = True
            write(line)
        elif mode == header:
            buffered.append(line)
            match = NS_LINE_RE.fullmatch(line) if short is not None else None
            if match:
                ns = int(match.group(1))
                if ns in keep:
                    write("".join(buffered))
                    stats.pages_kept += 1
                    mode = keeping
                else:
                    stats.pages_skipped += 1
                    stats.skipped_namespaces[str(ns)] = stats.skipped_namespaces.get(str(ns), 0) + 1
                    mode = dropping
                buffered = []
            elif short == _PAGE_CLOSE:
                write("".join(buffered))
                stats.pages_kept += 1
                buffered = []
                mode = outside
            elif len(buffered) > _MAX_PAGE_HEADER_LINES:
                raise DumpFormatError("<page> without <ns> near its start")
        elif mode == keeping:
            write(line)
            if short == _PAGE_CLOSE:
                mode = outside
        else:
            if short == _PAGE_CLOSE:
                mode = outside
    if mode != outside:
        raise DumpFormatError("dump ends inside a <page>")
    return stats


def verify_gzip_xml(path: Path) -> None:
    """Read the whole file back (gzip checks its CRC at the end) and make sure
    the XML is complete. Raises ValueError/OSError/EOFError."""
    tail = b""
    with gzip.open(path, "rb") as f:
        while True:
            chunk = f.read(DOWNLOAD_CHUNK)
            if not chunk:
                break
            tail = (tail + chunk)[-256:]
    if not tail.rstrip().endswith(b"</mediawiki>"):
        raise ValueError("filtered XML does not end with </mediawiki>")


def parse_7z_listing_size(output: str) -> Optional[int]:
    """Total uncompressed size from `7z l -slt`, or None if not found."""
    total = 0
    found = False
    in_entries = False
    for line in output.splitlines():
        if line.strip() == "----------":
            in_entries = True
            continue
        if in_entries and line.startswith("Size = "):
            try:
                total += int(line[len("Size = "):].strip())
                found = True
            except ValueError:
                continue
    return total if found else None


def parse_prepare_output(line: str) -> dict[str, Any]:
    """Validate the JSON line FandomImportPrepare prints last."""
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    namespaces = data.get("namespaces")
    if (not isinstance(namespaces, list) or not namespaces
            or not all(is_int(ns) for ns in namespaces)):
        raise ValueError("namespaces must be a non-empty list of integers")
    upload_user = validate_user_name(data.get("upload_user"))
    extensions = data.get("enabled_extensions", [])
    if not isinstance(extensions, list) or not all(isinstance(e, str) for e in extensions):
        raise ValueError("enabled_extensions must be a list of strings")
    created = data.get("created_namespaces", [])
    if not isinstance(created, list) or not all(
            isinstance(c, dict) and is_int(c.get("id")) and isinstance(c.get("name"), str)
            for c in created):
        raise ValueError("created_namespaces must be a list of {id, name}")
    warnings = data.get("warnings", [])
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        raise ValueError("warnings must be a list of strings")
    return {
        "namespaces": sorted(set(namespaces)),
        "upload_user": upload_user,
        "enabled_extensions": [clean_text(e, 255) for e in extensions],
        "created_namespaces": [{"id": c["id"], "name": clean_text(c["name"], 255)} for c in created],
        "warnings": [clean_text(w, 500) for w in warnings],
    }


class ImportImagesParser:
    """Reads importImages.php output line by line.

    Per file it prints "Importing <name>..." followed (normally on the same
    line) by "done.", "failed. (<reason>)" or "skipped. (...)"; at the end
    "Found: N", "Added: N", ... for every non-zero counter. It exits 1 when
    any file failed, or when no file had an allowed extension ("No suitable
    files could be found for import.").

    Output such as a PHP warning can land between the file name and its
    outcome; the name is then remembered until the outcome line arrives.
    """

    def __init__(self, keep_failed: int = FAILED_FILES_KEEP) -> None:
        self.counts: dict[str, int] = {}
        self.failed_files: list[str] = []
        self.failed_lines = 0
        self.done_lines = 0
        self.no_files = False
        self._keep = keep_failed
        self._pending: Optional[str] = None

    @property
    def has_summary(self) -> bool:
        return bool(self.counts)

    def feed(self, line: str) -> None:
        text = line.rstrip("\r\n")
        stripped = text.strip()
        match = IMPORTIMAGES_SUMMARY_RE.fullmatch(stripped)
        if match:
            self.counts[match.group(1).lower()] = int(match.group(2))
            return
        if "No suitable files could be found for import" in text:
            self.no_files = True
            return
        match = IMPORTIMAGES_LINE_RE.fullmatch(text)
        if match:
            outcome = match.group("outcome")
            if outcome is None:
                self._pending = match.group("name")
            else:
                self._pending = None
                self._outcome(match.group("name"), outcome)
            return
        if text.startswith("Importing ") and "..." in text:
            name = text[len("Importing "):text.index("...")]
            if "failed. (" in text:
                self._fail(name)
                self._pending = None
            else:
                self._pending = name
            return
        if self._pending is not None:
            if stripped.startswith("failed."):
                self._fail(self._pending)
                self._pending = None
            elif stripped == "done.":
                self.done_lines += 1
                self._pending = None
            elif stripped.startswith("skipped."):
                self._pending = None

    def _outcome(self, name: str, outcome: str) -> None:
        if outcome.startswith("failed"):
            self._fail(name)
        elif outcome == "done.":
            self.done_lines += 1

    def _fail(self, name: str) -> None:
        self.failed_lines += 1
        if len(self.failed_files) < self._keep:
            self.failed_files.append(clean_text(name, 255))

    def result(self) -> dict[str, Any]:
        failed = self.counts.get("failed", self.failed_lines)
        return {
            "found": self.counts.get("found", 0),
            "added": self.counts.get("added", self.done_lines),
            "skipped": self.counts.get("skipped", 0),
            "ignored": self.counts.get("ignored", 0),
            "overwritten": self.counts.get("overwritten", 0),
            "failed": failed,
            "failed_files": list(self.failed_files),
        }


def pick_next(states: Mapping[int, Mapping[str, Any]], queue: Sequence[tuple[int, float]],
              now: datetime) -> Optional[tuple[str, int]]:
    """Which import this run works on, if any.

    1. a running import whose next_try is due (crash recovery, backoff,
       disk waits),
    2. a waiting-dump import whose next_check is due,
    3. the oldest queued manifest (by mtime).

    Returns ("resume" | "recheck" | "claim", id) or None.
    """
    epoch = datetime.fromtimestamp(0, timezone.utc)
    running: list[tuple[datetime, int]] = []
    waiting: list[tuple[datetime, int]] = []
    for import_id, st in states.items():
        status = st.get("status")
        if status == STATUS_RUNNING:
            due = parse_iso(st.get("next_try")) or epoch
            if due <= now:
                running.append((due, import_id))
        elif status == STATUS_WAITING_DUMP:
            due = parse_iso(st.get("next_check")) or epoch
            if due <= now:
                waiting.append((due, import_id))
    if running:
        return "resume", min(running)[1]
    if waiting:
        return "recheck", min(waiting)[1]
    if queue:
        _mtime, import_id = min((mtime, import_id) for import_id, mtime in queue)
        return "claim", import_id
    return None


@dataclass(frozen=True)
class Config:
    spool_dir: Path
    central_wiki: str
    php: str
    mwscript: str
    proxy: str
    user_agent: str
    image_delay: float = 1.0
    retries: int = 5
    max_stage_attempts: int = 3
    min_free_bytes: int = 10 * GiB
    disk_headroom_bytes: int = 5 * GiB
    failed_retention_days: float = 3
    log_retention_days: float = 30
    dump_recheck_hours: float = 24
    dump_max_wait_days: float = 14
    prefer_full_history: bool = True
    wikiteam3: str = "wikiteam3dumpgenerator"
    sevenzip: str = "7z"

    @classmethod
    def load(cls, path: Path) -> "Config":
        data = read_json_file(path, MAX_MANIFEST_BYTES)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: not a JSON object")
        for key in ("spool_dir", "central_wiki", "php", "mwscript", "proxy", "user_agent"):
            if not isinstance(data.get(key), str) or not data[key]:
                raise ValueError(f"{path}: {key} is required")
        spool = Path(data["spool_dir"])
        if not spool.is_absolute():
            raise ValueError(f"{path}: spool_dir must be absolute")
        if not DBNAME_RE.fullmatch(data["central_wiki"]):
            raise ValueError(f"{path}: central_wiki is invalid")
        defaults = cls(spool, "x", "x", "x", "x", "x")
        return cls(
            spool_dir=spool,
            central_wiki=data["central_wiki"],
            php=data["php"],
            mwscript=data["mwscript"],
            proxy=data["proxy"],
            user_agent=data["user_agent"],
            image_delay=float(data.get("image_delay", defaults.image_delay)),
            retries=int(data.get("retries", defaults.retries)),
            max_stage_attempts=max(1, int(data.get("max_stage_attempts", defaults.max_stage_attempts))),
            min_free_bytes=int(data.get("min_free_bytes", defaults.min_free_bytes)),
            disk_headroom_bytes=int(data.get("disk_headroom_bytes", defaults.disk_headroom_bytes)),
            failed_retention_days=float(data.get("failed_retention_days", defaults.failed_retention_days)),
            log_retention_days=float(data.get("log_retention_days", defaults.log_retention_days)),
            dump_recheck_hours=float(data.get("dump_recheck_hours", defaults.dump_recheck_hours)),
            dump_max_wait_days=float(data.get("dump_max_wait_days", defaults.dump_max_wait_days)),
            prefer_full_history=bool(data.get("prefer_full_history", defaults.prefer_full_history)),
            wikiteam3=str(data.get("wikiteam3", defaults.wikiteam3)),
            sevenzip=str(data.get("sevenzip", defaults.sevenzip)),
        )

    @property
    def queue_dir(self) -> Path:
        return self.spool_dir / "queue"

    @property
    def work_dir(self) -> Path:
        return self.spool_dir / "work"

    @property
    def logs_dir(self) -> Path:
        return self.spool_dir / "logs"

    @property
    def tmp_dir(self) -> Path:
        return self.spool_dir / "tmp"

    @property
    def lock_path(self) -> Path:
        return self.spool_dir / "worker.lock"


def _utc_formatter() -> logging.Formatter:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%SZ")
    formatter.converter = time.gmtime
    return formatter


class ImportLog:
    """logs/<id>.log. Tool output and detail go there only; `event()` lines
    are also echoed to stderr, which cron appends to logs/worker.log."""

    def __init__(self, logs_dir: Path, import_id: int) -> None:
        self.import_id = import_id
        self._logger = logging.getLogger(f"fandom_import.import.{import_id}")
        self._logger.propagate = False
        self._logger.setLevel(logging.INFO)
        for handler in list(self._logger.handlers):
            self._logger.removeHandler(handler)
            handler.close()
        self._handler = logging.FileHandler(logs_dir / f"{import_id}.log", encoding="utf-8", delay=True)
        self._handler.setFormatter(_utc_formatter())
        self._logger.addHandler(self._handler)

    def info(self, msg: str) -> None:
        self._logger.info(msg)

    def warning(self, msg: str) -> None:
        self._logger.warning(msg)

    def event(self, level: int, msg: str) -> None:
        self._logger.log(level, msg)
        LOG.log(level, f"import {self.import_id}: {msg}")

    def tool(self, label: str, line: str) -> None:
        self._logger.info(f"{label}| {line}")

    def close(self) -> None:
        self._logger.removeHandler(self._handler)
        self._handler.close()


@dataclass
class ToolResult:
    returncode: int
    terminated: Optional[str]
    tail: list[str]

    def last_line(self) -> str:
        for line in reversed(self.tail):
            if line.strip():
                return clean_text(line, 300)
        return ""


def terminate_process_group(proc: subprocess.Popen, grace: float = 30) -> None:
    """SIGTERM the tool's process group, SIGKILL it if it lingers."""
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 10.0)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            proc.send_signal(sig)
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def run_streaming(cmd: Sequence[str], *, env: Mapping[str, str], cwd: Path,
                  on_line: Callable[[str], None],
                  on_poll: Optional[Callable[[], Optional[str]]] = None,
                  poll_seconds: float = POLL_INTERVAL, pass_fds: Sequence[int] = (),
                  stderr_path: Optional[Path] = None) -> ToolResult:
    """Run a tool, hand every output line to `on_line` (from a reader thread)
    and call `on_poll` from this thread every `poll_seconds`. If `on_poll`
    returns a reason, the tool is terminated and the reason is reported.

    The tool gets its own process group so it can be killed as a whole, and
    inherits the worker lock (pass_fds): if the worker itself is SIGKILLed, an
    orphaned tool keeps the lock held until it exits, so the next cron run
    cannot start a second copy on the same files. An exception in `on_line`
    is logged and never stops the pipe from being drained.
    """
    tail: deque[str] = deque(maxlen=40)
    stderr_file = open(stderr_path, "ab") if stderr_path else None
    try:
        proc = subprocess.Popen(
            list(cmd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=stderr_file if stderr_file else subprocess.STDOUT,
            env=dict(env), cwd=str(cwd), pass_fds=tuple(pass_fds), start_new_session=True,
        )
    finally:
        if stderr_file:
            stderr_file.close()

    def pump() -> None:
        assert proc.stdout is not None
        with proc.stdout:
            for raw in iter(lambda: proc.stdout.readline(MAX_TOOL_LINE), b""):
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                tail.append(line)
                try:
                    on_line(line)
                except Exception:
                    LOG.exception("output handler failed")

    reader = threading.Thread(target=pump, name="tool-output", daemon=True)
    reader.start()
    terminated: Optional[str] = None
    try:
        while True:
            try:
                proc.wait(timeout=poll_seconds)
                break
            except subprocess.TimeoutExpired:
                pass
            if on_poll is not None:
                reason = on_poll()
                if reason:
                    terminated = reason
                    terminate_process_group(proc)
                    break
    finally:
        if proc.poll() is None:
            terminate_process_group(proc)
        reader.join(timeout=30)
    return ToolResult(proc.returncode, terminated, list(tail))


class MediaWiki:
    """Builds maintenance-script command lines the way the job runner does."""

    def __init__(self, php: str, mwscript: str) -> None:
        self.php = php
        self.mwscript = mwscript

    def command(self, script: str, wiki: str, *args: str) -> list[str]:
        return [self.php, self.mwscript, "maintenance/run.php", script, f"--wiki={wiki}", *args]

    def callback_command(self, central_wiki: str, import_id: int, event: str, *,
                         stage: Optional[str] = None, data: Optional[dict[str, Any]] = None,
                         message: Optional[str] = None) -> list[str]:
        args = [f"--id={import_id}", f"--event={event}"]
        if stage:
            args.append(f"--stage={stage}")
        if data is not None:
            args.append("--data=" + json.dumps(data, separators=(",", ":"), sort_keys=True))
        if message:
            args.append("--message=" + clean_text(message, 1000))
        return self.command("WikiOasisMagic:FandomImportCallback", central_wiki, *args)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects become HTTPErrors. A redirect would mean fetching a URL that
    neither the manifest nor this worker built (a renamed or closed wiki
    redirects elsewhere on Fandom); it is reported instead of followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class DumpCheck:
    variant: str
    url: str
    status: Optional[int]
    storage_class: Optional[str] = None
    restored: bool = False
    last_modified: Optional[str] = None
    content_length: Optional[int] = None
    md5: Optional[str] = None
    etag: Optional[str] = None

    @property
    def usable(self) -> bool:
        if self.status != 200:
            return False
        cold = (self.storage_class or "").upper() in UNUSABLE_STORAGE_CLASSES
        return not cold or self.restored

    def describe(self) -> str:
        text = f"HTTP {self.status}"
        if self.storage_class:
            text += f", storage class {self.storage_class}"
        return text

    def to_callback(self) -> dict[str, Any]:
        return {"variant": self.variant, "status": self.status,
                "storage_class": self.storage_class, "last_modified": self.last_modified}


def _http_date_to_iso(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return iso(email.utils.parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None


class Http:
    def __init__(self, proxy: str, user_agent: str, retries: int,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.user_agent = user_agent
        self.retries = max(0, retries)
        self.sleep = sleep
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}), _NoRedirect())

    def _backoff(self, attempt: int, retry_after: Optional[str]) -> float:
        if retry_after and retry_after.strip().isdigit():
            return min(int(retry_after.strip()), 300)
        return min(2 ** attempt * 2, 60)

    def open(self, url: str, *, headers: Optional[Mapping[str, str]] = None,
             method: str = "GET", timeout: float = API_TIMEOUT):
        req = urllib.request.Request(url, method=method,
                                     headers={"User-Agent": self.user_agent, **(headers or {})})
        return self.opener.open(req, timeout=timeout)

    def get_json(self, url: str, params: Mapping[str, str], *, timeout: float = API_TIMEOUT) -> Any:
        """GET a MediaWiki API URL, retrying 429/5xx and network errors."""
        full = url + "?" + urllib.parse.urlencode(params)
        last = ""
        for attempt in range(self.retries + 1):
            wait = self._backoff(attempt, None)
            try:
                with self.open(full, headers={"Accept": "application/json"}, timeout=timeout) as resp:
                    raw = resp.read(MAX_JSON_BYTES + 1)
                if len(raw) > MAX_JSON_BYTES:
                    raise StageError(f"{url}: response larger than {MAX_JSON_BYTES} bytes")
                try:
                    data = json.loads(raw)
                except ValueError:
                    raise StageError(f"{url}: response is not JSON") from None
                error = data.get("error") if isinstance(data, dict) else None
                if isinstance(error, dict):
                    code = clean_text(error.get("code", "?"), 80)
                    if code in ("maxlag", "ratelimited"):
                        last = f"API error {code}"
                    else:
                        raise StageError(f"{url}: API error {code}: {clean_text(error.get('info', ''), 200)}")
                else:
                    return data
            except urllib.error.HTTPError as e:
                status, location, retry_after = e.code, e.headers.get("Location"), e.headers.get("Retry-After")
                e.close()
                if 300 <= status < 400:
                    raise StageError(f"{url} redirects to {clean_text(location or '?', 200)}; "
                                     f"the wiki may have moved or been renamed", permanent=True) from None
                if status in (404, 410):
                    raise StageError(f"{url} returned HTTP {status}; the wiki does not seem to exist",
                                     permanent=True) from None
                if status != 429 and status < 500:
                    raise StageError(f"{url} returned HTTP {status}") from None
                last = f"HTTP {status}"
                wait = self._backoff(attempt, retry_after)
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
                last = clean_text(e, 200)
            if attempt < self.retries:
                self.sleep(wait)
        raise StageError(f"giving up on {url} after {self.retries + 1} tries: {last}")

    def head(self, url: str, *, timeout: float = API_TIMEOUT) -> tuple[int, Any]:
        """(status, headers) for a HEAD request. 3xx/4xx are results, not errors."""
        last = ""
        for attempt in range(self.retries + 1):
            wait = self._backoff(attempt, None)
            try:
                with self.open(url, method="HEAD", timeout=timeout) as resp:
                    return resp.status, resp.headers
            except urllib.error.HTTPError as e:
                status, headers = e.code, e.headers
                e.close()
                if status != 429 and status < 500:
                    return status, headers
                last = f"HTTP {status}"
                wait = self._backoff(attempt, headers.get("Retry-After"))
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
                last = clean_text(e, 200)
            if attempt < self.retries:
                self.sleep(wait)
        raise StageError(f"HEAD {url} failed after {self.retries + 1} tries: {last}")


class WorkerLock:
    """flock() on <spool>/worker.lock. Non-blocking: a second run just exits."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: Optional[int] = None

    def acquire(self) -> bool:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o640)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        self.fd = fd
        return True

    def release(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class Worker:
    def __init__(self, cfg: Config, *, clock: Callable[[], datetime] = utcnow) -> None:
        self.cfg = cfg
        self.clock = clock
        self.mw = MediaWiki(cfg.php, cfg.mwscript)
        self.child_fds: tuple[int, ...] = ()
        self.active_id: Optional[int] = None
        self._http: Optional[Http] = None
        self._logs: dict[int, ImportLog] = {}
        self._last_housekeeping = 0.0

    @property
    def http(self) -> Http:
        if self._http is None:
            self._http = Http(self.cfg.proxy, self.cfg.user_agent, self.cfg.retries)
        return self._http

    def log_for(self, import_id: int) -> ImportLog:
        if import_id not in self._logs:
            self._logs[import_id] = ImportLog(self.cfg.logs_dir, import_id)
        return self._logs[import_id]

    def close_logs(self) -> None:
        for log in self._logs.values():
            log.close()
        self._logs.clear()

    def work_dir(self, import_id: int) -> Path:
        return self.cfg.work_dir / str(import_id)

    def state_path(self, import_id: int) -> Path:
        return self.work_dir(import_id) / "state.json"

    def manifest_path(self, import_id: int) -> Path:
        return self.work_dir(import_id) / "manifest.json"

    def incoming_path(self, import_id: int) -> Path:
        return self.work_dir(import_id) / "incoming.json"

    def tmp_dir(self, import_id: int) -> Path:
        return self.work_dir(import_id) / "tmp"

    def rmtree(self, path: Path, log: Optional[ImportLog] = None) -> int:
        return safe_rmtree(path, (self.cfg.work_dir, self.cfg.queue_dir),
                           log=log.info if log else None)

    def ensure_dirs(self) -> None:
        if not self.cfg.spool_dir.is_dir():
            raise RuntimeError(f"spool directory {self.cfg.spool_dir} does not exist")
        for d in (self.cfg.queue_dir, self.cfg.work_dir, self.cfg.logs_dir, self.cfg.tmp_dir):
            d.mkdir(mode=0o750, exist_ok=True)

    def child_env(self, tmpdir: Path, *, network: bool = False) -> dict[str, str]:
        """A clean environment: nothing from cron's leaks in, temp files stay
        in the spool, and only network tools get the proxy (PHP must not send
        MediaWiki's own internal traffic through squid)."""
        env = {
            "PATH": CHILD_PATH,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TMPDIR": str(tmpdir),
            "HOME": str(tmpdir),
            "PYTHONUNBUFFERED": "1",
        }
        if network:
            for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
                env[key] = self.cfg.proxy
            env["no_proxy"] = env["NO_PROXY"] = "localhost,127.0.0.1,::1"
        return env

    def new_state(self, import_id: int, manifest: Optional[Manifest] = None) -> dict[str, Any]:
        now = iso(self.clock())
        return {
            "version": 1,
            "id": import_id,
            "central_wiki": self.cfg.central_wiki,
            "target_wiki": manifest.target_wiki if manifest else None,
            "source_key": manifest.source.key if manifest else None,
            "status": STATUS_RUNNING,
            "stage": STAGES[0],
            "completed": [],
            "announced_stage": None,
            "attempts": {},
            "interruptions": {},
            "inflight": None,
            "next_try": None,
            "waiting_for": None,
            "next_check": None,
            "waiting_since": None,
            "failed_at": None,
            "files_expire": None,
            "error": None,
            "summary": {},
            "stage_data": {},
            "pending_callbacks": [],
            "callback_failures": 0,
            "callback_retry_at": None,
            "pending_progress": None,
            "last_progress_at": 0,
            "created_at": now,
            "updated_at": now,
        }

    def load_state(self, import_id: int) -> Optional[dict[str, Any]]:
        try:
            data = read_json_file(self.state_path(import_id), MAX_JSON_BYTES)
        except (OSError, ValueError):
            return None
        if (not isinstance(data, dict) or data.get("id") != import_id
                or data.get("status") not in KNOWN_STATUSES
                or not isinstance(data.get("central_wiki"), str)
                or not DBNAME_RE.fullmatch(data["central_wiki"])
                or not isinstance(data.get("pending_callbacks", []), list)):
            return None
        state = self.new_state(import_id)
        state.update(data)
        return state

    def save_state(self, st: dict[str, Any]) -> None:
        st["updated_at"] = iso(self.clock())
        write_json_atomic(self.state_path(st["id"]), st)

    def load_manifest(self, import_id: int) -> Manifest:
        data = read_json_file(self.manifest_path(import_id), MAX_MANIFEST_BYTES)
        return validate_manifest(data, expected_id=import_id, central_wiki=self.cfg.central_wiki)

    def work_ids(self) -> list[int]:
        ids = []
        for entry in self.cfg.work_dir.iterdir():
            if ID_RE.fullmatch(entry.name) and entry.is_dir() and not entry.is_symlink():
                ids.append(int(entry.name))
        return sorted(ids)

    def purge_work_files(self, import_id: int, keep: Collection[str] = TOMBSTONE_KEEP) -> int:
        """Delete everything in work/<id> except `keep`. Returns bytes freed."""
        log = self.log_for(import_id)
        freed = 0
        wd = self.work_dir(import_id)
        if not wd.is_dir():
            return 0
        for entry in sorted(wd.iterdir()):
            if entry.name in keep:
                continue
            try:
                freed += self.rmtree(entry, log)
            except UnsafePathError as e:
                log.event(logging.ERROR, str(e))
        return freed

    def finish_tombstone(self, st: dict[str, Any]) -> bool:
        """Remove a tombstone's work dir once nothing is left to deliver."""
        if st["status"] not in TOMBSTONE_STATUSES or st.get("pending_callbacks"):
            return False
        wd = self.work_dir(st["id"])
        if wd.exists():
            self.rmtree(wd, self.log_for(st["id"]))
        return True

    def _deliver(self, st: dict[str, Any], cb: Mapping[str, Any]) -> bool:
        import_id = st["id"]
        log = self.log_for(import_id)
        cmd = self.mw.callback_command(st["central_wiki"], import_id, cb["event"],
                                       stage=cb.get("stage"), data=cb.get("data"),
                                       message=cb.get("message"))
        wd = self.work_dir(import_id)
        tmp = self.tmp_dir(import_id)
        if not tmp.is_dir():
            tmp = self.cfg.tmp_dir
        try:
            proc = subprocess.run(
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=self.child_env(tmp), cwd=str(wd if wd.is_dir() else self.cfg.spool_dir),
                timeout=CALLBACK_TIMEOUT, pass_fds=self.child_fds,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            log.event(logging.WARNING, f"callback {cb['event']} failed: {clean_text(e, 300)}")
            return False
        if proc.returncode != 0:
            output = proc.stdout.decode("utf-8", "replace")[-500:]
            log.event(logging.WARNING, f"callback {cb['event']} exited {proc.returncode}: {clean_text(output, 500)}")
            return False
        log.info(f"callback {cb['event']} delivered")
        return True

    def queue_callback(self, st: dict[str, Any], event: str, *, stage: Optional[str] = None,
                       data: Optional[dict[str, Any]] = None, message: Optional[str] = None) -> None:
        """Persist a terminal callback; flush_callbacks() delivers it in order.

        Any queued waiting-dump notice is dropped first: it is stale the
        moment anything newer happens to the import.
        """
        assert event in TERMINAL_EVENTS
        pending = [c for c in st.get("pending_callbacks") or [] if c.get("event") != "waiting-dump"]
        entry: dict[str, Any] = {"event": event, "queued_at": iso(self.clock())}
        if stage:
            entry["stage"] = stage
        if data is not None:
            entry["data"] = data
        if message:
            entry["message"] = clean_text(message, 1000)
        pending.append(entry)
        st["pending_callbacks"] = pending
        st["callback_retry_at"] = None
        self.save_state(st)

    def flush_callbacks(self, st: dict[str, Any], *, force: bool = False) -> bool:
        """Deliver queued terminal callbacks in order. True when none are left."""
        pending = st.get("pending_callbacks") or []
        if not pending:
            return True
        retry_at = parse_iso(st.get("callback_retry_at"))
        if retry_at and retry_at > self.clock() and not force:
            return False
        while pending:
            if not self._deliver(st, pending[0]):
                failures = int(st.get("callback_failures") or 0) + 1
                st["callback_failures"] = failures
                delay = min(60 * 2 ** (failures - 1), CALLBACK_BACKOFF_MAX)
                st["callback_retry_at"] = iso(self.clock() + timedelta(seconds=delay))
                self.save_state(st)
                return False
            pending.pop(0)
            st["pending_callbacks"] = pending
            st["callback_failures"] = 0
            st["callback_retry_at"] = None
            self.save_state(st)
        return True

    def notify(self, st: dict[str, Any], event: str, *, stage: Optional[str] = None,
               data: Optional[dict[str, Any]] = None, message: Optional[str] = None) -> bool:
        """Best-effort, non-terminal callback. Skipped while terminal callbacks
        are still queued, so it can never overtake one of them."""
        if not self.flush_callbacks(st):
            self.log_for(st["id"]).info(f"not sending {event}: earlier callbacks are still queued")
            return False
        return self._deliver(st, {"event": event, "stage": stage, "data": data, "message": message})

    def progress(self, st: dict[str, Any], data: Optional[Mapping[str, Any]] = None,
                 message: Optional[str] = None) -> None:
        """Merge into the pending progress update and send it if allowed."""
        pending = st.get("pending_progress") or {"data": {}, "message": None}
        if data:
            pending["data"].update(data)
        if message:
            pending["message"] = message
        st["pending_progress"] = pending
        self.flush_progress(st)

    def flush_progress(self, st: dict[str, Any]) -> None:
        """Send the pending progress update if the throttle allows, else keep
        it in state.json for later. Best effort: an update that fails to send
        is dropped, since `done` carries the full summary anyway."""
        pending = st.get("pending_progress")
        if not pending:
            return
        now = self.clock().timestamp()
        if now - float(st.get("last_progress_at") or 0) >= PROGRESS_INTERVAL:
            st["pending_progress"] = None
            st["last_progress_at"] = now
            self.notify(st, "progress", data=pending.get("data") or None, message=pending.get("message"))
        if self.work_dir(st["id"]).is_dir():
            self.save_state(st)

    def queue_entries(self) -> list[tuple[int, float]]:
        """(id, mtime) for queued manifests, including claims a crash
        interrupted (work/<id>/incoming.json; os.replace keeps the mtime)."""
        entries: dict[int, float] = {}
        for path in self.cfg.queue_dir.iterdir():
            match = QUEUE_MANIFEST_RE.fullmatch(path.name)
            if not match:
                continue
            try:
                st = os.lstat(path)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(st.st_mode):
                entries[int(match.group(1))] = st.st_mtime
        for import_id in self.work_ids():
            try:
                st = os.lstat(self.incoming_path(import_id))
            except FileNotFoundError:
                continue
            if stat.S_ISREG(st.st_mode):
                entries[import_id] = min(entries.get(import_id, st.st_mtime), st.st_mtime)
        return sorted(entries.items())

    def claim(self, import_id: int) -> Optional[dict[str, Any]]:
        """Move queue/<id>.json into work/<id>/ and set up state for it.

        A manifest for an id that is failed, waiting for a dump or backing
        off is a retry: attempts are reset but completed stages are kept.
        """
        log = self.log_for(import_id)
        wd = self.work_dir(import_id)
        queued = self.cfg.queue_dir / f"{import_id}.json"
        incoming = self.incoming_path(import_id)
        try:
            if wd.is_symlink() or (wd.exists() and not wd.is_dir()):
                raise UnsafePathError(f"{wd} is not a directory")
            wd.mkdir(mode=0o750, exist_ok=True)
            if queued.exists():
                os.replace(queued, incoming)
        except (OSError, UnsafePathError) as e:
            log.event(logging.ERROR, f"cannot claim manifest: {e}")
            try:
                self.rmtree(queued, log)
            except (OSError, UnsafePathError):
                pass
            self.reject(import_id, ManifestError(f"worker could not claim the request: {e}",
                                                 import_id, self.cfg.central_wiki))
            return None
        if not incoming.is_file():
            return None

        try:
            manifest = validate_manifest(read_json_file(incoming, MAX_MANIFEST_BYTES),
                                         expected_id=import_id, central_wiki=self.cfg.central_wiki)
        except (OSError, ValueError) as e:
            self.rmtree(incoming, log)
            err = e if isinstance(e, ManifestError) else ManifestError(f"unreadable manifest: {e}")
            self.reject(import_id, err)
            return None

        st = self.load_state(import_id)
        old_manifest: Optional[Manifest] = None
        if st is not None:
            try:
                old_manifest = self.load_manifest(import_id)
            except (OSError, ValueError):
                old_manifest = None
        resumable = (
            st is not None and st["status"] not in TOMBSTONE_STATUSES and old_manifest is not None
            and old_manifest.target_wiki == manifest.target_wiki
            and old_manifest.source == manifest.source
        )
        if resumable:
            assert st is not None
            log.event(logging.INFO, f"retry requested; resuming from {self._next_stage(st)} "
                                    f"(was {st['status']})")
            self.reset_for_retry(st)
        else:
            carried = [c for c in (st or {}).get("pending_callbacks", [])
                       if c.get("event") not in ("failed", "waiting-dump")]
            if st is not None:
                log.event(logging.INFO, f"starting over (previous state was {st['status']})")
                self.purge_work_files(import_id, keep={"incoming.json", "state.json"})
            st = self.new_state(import_id, manifest)
            st["pending_callbacks"] = carried
        st["target_wiki"] = manifest.target_wiki
        st["source_key"] = manifest.source.key
        self.tmp_dir(import_id).mkdir(mode=0o750, exist_ok=True)
        self.save_state(st)
        os.replace(incoming, self.manifest_path(import_id))
        log.event(logging.INFO, f"claimed: {manifest.source.base_url} -> {manifest.target_wiki}")
        stage = self._next_stage(st)
        self.notify(st, "started", stage=stage)
        st["announced_stage"] = stage
        self.save_state(st)
        return st

    @staticmethod
    def _next_stage(st: Mapping[str, Any]) -> str:
        done = set(st.get("completed") or [])
        return next((s for s in STAGES if s not in done), STAGES[-1])

    def reset_for_retry(self, st: dict[str, Any]) -> None:
        st.update(status=STATUS_RUNNING, attempts={}, interruptions={}, inflight=None,
                  next_try=None, waiting_for=None, next_check=None, waiting_since=None,
                  failed_at=None, files_expire=None, error=None, announced_stage=None)
        st["pending_callbacks"] = [c for c in st.get("pending_callbacks") or []
                                   if c.get("event") not in ("failed", "waiting-dump")]

    def reject(self, import_id: int, err: ManifestError) -> None:
        """Report an unusable manifest as `failed`, if it can be attributed.

        With no import yet there is no stage, so the callback says "resolve"
        to keep --stage present for a callback script that may require it.
        An invalid retry request for an import that is still running or
        waiting for a dump is only logged, so it cannot contradict that import.
        """
        log = self.log_for(import_id)
        log.event(logging.WARNING, f"rejected manifest: {err}")
        wd = self.work_dir(import_id)
        st = self.load_state(import_id)
        if err.import_id != import_id or err.central_wiki != self.cfg.central_wiki:
            if st is None and wd.is_dir() and not wd.is_symlink() and not any(wd.iterdir()):
                self.rmtree(wd, log)
            return
        message = f"Invalid import request: {err}"
        if st is None:
            if wd.is_dir() and not wd.is_symlink():
                self.purge_work_files(import_id, keep=())
            wd.mkdir(mode=0o750, exist_ok=True)
            st = self.new_state(import_id)
            st["status"] = STATUS_REJECTED
            self.queue_callback(st, "failed", stage=STAGES[0], message=message,
                                data={"files_expire": None})
        elif st["status"] in (STATUS_RUNNING, STATUS_WAITING_DUMP):
            log.warning("ignoring the invalid retry request; the import is still active")
            return
        else:
            expire = st.get("files_expire") if st["status"] == STATUS_FAILED else None
            self.queue_callback(st, "failed", stage=st.get("stage") or STAGES[0], message=message,
                                data={"files_expire": expire})
        self.flush_callbacks(st, force=True)
        self.finish_tombstone(st)

    def process_discards(self) -> None:
        """Handle every queue/<id>.discard. The import this process is
        running is skipped; its discard is picked up once that run ends."""
        for path in sorted(self.cfg.queue_dir.iterdir()):
            match = QUEUE_DISCARD_RE.fullmatch(path.name)
            if not match:
                continue
            import_id = int(match.group(1))
            if import_id == self.active_id:
                continue
            try:
                validate_discard(read_json_file(path, MAX_MANIFEST_BYTES), import_id, self.cfg.central_wiki)
            except (OSError, ValueError) as e:
                LOG.warning(f"ignoring invalid discard request {path.name}: {clean_text(e, 200)}")
                self.rmtree(path)
                continue
            try:
                self.discard(import_id, path)
            except (OSError, UnsafePathError) as e:
                LOG.error(f"discarding import {import_id} failed: {clean_text(e, 300)}")

    def discard(self, import_id: int, discard_path: Path) -> None:
        """Delete an import's working files and report `files-deleted`.

        A queued retry request older than the discard is superseded by it and
        deleted too. The discard request itself is removed only after the
        `files-deleted` callback is persisted, so a crash cannot lose it.
        """
        log = self.log_for(import_id)
        log.event(logging.INFO, "discard requested; deleting working files")
        discard_mtime = discard_path.stat().st_mtime
        queued = self.cfg.queue_dir / f"{import_id}.json"
        try:
            if queued.stat().st_mtime <= discard_mtime:
                self.rmtree(queued, log)
        except FileNotFoundError:
            pass
        wd = self.work_dir(import_id)
        st = self.load_state(import_id)
        if st is None:
            if wd.exists():
                self.rmtree(wd, log)
            wd.mkdir(mode=0o750)
            st = self.new_state(import_id)
        else:
            if st["status"] in (STATUS_RUNNING, STATUS_WAITING_DUMP):
                st.update(status=STATUS_FAILED, failed_at=iso(self.clock()), files_expire=None,
                          error="Import discarded", next_try=None, inflight=None)
                self.queue_callback(st, "failed", stage=st.get("stage"), message="Import discarded",
                                    data={"files_expire": None})
            self.purge_work_files(import_id)
        st["status"] = STATUS_DELETED
        st["pending_progress"] = None
        self.queue_callback(st, "files-deleted")
        self.rmtree(discard_path, log)
        self.flush_callbacks(st, force=True)
        self.finish_tombstone(st)

    def cleanup_work(self) -> None:
        """Expire failed imports, retry queued callbacks, drop orphans.

        A work dir holding only incoming.json is an interrupted claim, not an
        orphan: pick_next() treats it as a queued manifest and finishes it.
        """
        now = self.clock()
        for entry in sorted(self.cfg.work_dir.iterdir()):
            import_id = int(entry.name) if ID_RE.fullmatch(entry.name) else None
            if import_id is not None and import_id == self.active_id:
                continue
            if entry.is_symlink():
                LOG.warning(f"leaving symlink {entry} alone; it should not be there")
                continue
            st = self.load_state(import_id) if import_id is not None and entry.is_dir() else None
            if st is None:
                if import_id is not None and self.incoming_path(import_id).is_file():
                    continue
                try:
                    age = now.timestamp() - os.lstat(entry).st_mtime
                except FileNotFoundError:
                    continue
                if age > ORPHAN_AGE:
                    LOG.warning(f"removing orphan {entry} (no valid state.json)")
                    try:
                        self.rmtree(entry)
                    except (OSError, UnsafePathError) as e:
                        LOG.error(f"could not remove {entry}: {clean_text(e, 300)}")
                continue
            try:
                self._cleanup_one(st, now)
            except (OSError, UnsafePathError) as e:
                LOG.error(f"cleanup of import {st['id']} failed: {clean_text(e, 300)}")

    def _cleanup_one(self, st: dict[str, Any], now: datetime) -> None:
        if st["status"] == STATUS_FAILED:
            expire = parse_iso(st.get("files_expire"))
            if expire is not None and expire <= now:
                log = self.log_for(st["id"])
                freed = self.purge_work_files(st["id"])
                log.event(logging.INFO, f"failed import's files expired; {human_bytes(freed)} freed")
                st["status"] = STATUS_DELETED
                st["pending_progress"] = None
                self.queue_callback(st, "files-deleted")
        self.flush_callbacks(st)
        if st.get("pending_progress"):
            self.flush_progress(st)
        self.finish_tombstone(st)

    def housekeeping(self) -> None:
        self.process_discards()
        self.cleanup_work()

    def maybe_housekeep(self) -> None:
        """Called from long poll loops so a multi-day import doesn't stall
        everyone else's discards, expiries and callbacks."""
        if time.monotonic() - self._last_housekeeping < HOUSEKEEPING_INTERVAL:
            return
        self._last_housekeeping = time.monotonic()
        try:
            self.housekeeping()
        except Exception:
            LOG.exception("housekeeping failed")

    def cmd_run(self) -> int:
        lock = WorkerLock(self.cfg.lock_path)
        if not lock.acquire():
            return 0
        assert lock.fd is not None
        self.child_fds = (lock.fd,)
        try:
            self.ensure_dirs()
            self.housekeeping()
            self._last_housekeeping = time.monotonic()
            states = {}
            for import_id in self.work_ids():
                st = self.load_state(import_id)
                if st is not None:
                    states[import_id] = st
            choice = pick_next(states, self.queue_entries(), self.clock())
            if choice is None:
                return 0
            kind, import_id = choice
            st = self.claim(import_id) if kind == "claim" else states[import_id]
            if st is not None:
                ImportRunner(self, st).run(recheck=(kind == "recheck"))
            return 0
        finally:
            self.child_fds = ()
            lock.release()

    def cmd_janitor(self) -> int:
        """Daily: expire logs/<id>.log and stray queue/tmp files, then do the
        `run` housekeeping if no import holds the lock. worker.log and its
        rotations are left to logrotate."""
        now = self.clock().timestamp()
        self.ensure_dirs()
        logs_cutoff = now - self.cfg.log_retention_days * 86400
        for path in sorted(self.cfg.logs_dir.iterdir()):
            if not IMPORT_LOG_RE.fullmatch(path.name):
                continue
            try:
                st = os.lstat(path)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_mtime < logs_cutoff:
                safe_rmtree(path, (self.cfg.logs_dir,))
        for path in sorted(self.cfg.queue_dir.iterdir()):
            if path.name.startswith(".tmp-") or path.name.endswith(".part"):
                self._remove_if_older(path, now - STRAY_AGE, (self.cfg.queue_dir,))
            elif not (QUEUE_MANIFEST_RE.fullmatch(path.name) or QUEUE_DISCARD_RE.fullmatch(path.name)):
                LOG.warning(f"unexpected file in queue/: {path.name}")
        for path in sorted(self.cfg.tmp_dir.iterdir()):
            self._remove_if_older(path, now - STRAY_AGE, (self.cfg.tmp_dir,))

        lock = WorkerLock(self.cfg.lock_path)
        if not lock.acquire():
            LOG.info("janitor: an import is running and does its own housekeeping")
            return 0
        assert lock.fd is not None
        self.child_fds = (lock.fd,)
        try:
            self.housekeeping()
        finally:
            self.child_fds = ()
            lock.release()
        return 0

    @staticmethod
    def _remove_if_older(path: Path, cutoff: float, roots: tuple[Path, ...]) -> None:
        try:
            if os.lstat(path).st_mtime < cutoff:
                safe_rmtree(path, roots)
        except FileNotFoundError:
            pass
        except UnsafePathError as e:
            LOG.warning(str(e))


class ImportRunner:
    """Runs one import's stages until it is done, failed, waiting or paused.

    `manifest` is loaded (and validated again) at the start of run().
    """

    def __init__(self, worker: Worker, st: dict[str, Any]) -> None:
        self.w = worker
        self.cfg = worker.cfg
        self.st = st
        self.id: int = st["id"]
        self.log = worker.log_for(self.id)
        self.dir = worker.work_dir(self.id)
        self.tmp = worker.tmp_dir(self.id)
        self.manifest: Manifest

    def run(self, *, recheck: bool = False) -> None:
        """Run stages in order, persisting state after each.

        A stage still marked in flight means the previous worker died inside
        it; that counts as an interruption, not a failed attempt. Leaving
        waiting-dump drops any undelivered waiting-dump notice (it would now
        be wrong) and re-announces the stage so MediaWiki shows it running.
        SIGTERM/SIGINT unwind without counting an attempt, so the next run
        resumes the same stage.
        """
        self.w.active_id = self.id
        try:
            self._run(recheck)
        finally:
            self.w.active_id = None

    def _run(self, recheck: bool) -> None:
        st = self.st
        try:
            self.manifest = self.w.load_manifest(self.id)
        except (OSError, ValueError) as e:
            self.fail(st.get("stage") or STAGES[0], f"Stored manifest is unusable: {clean_text(e, 300)}")
            return
        self.tmp.mkdir(mode=0o750, exist_ok=True)
        self.w.flush_callbacks(st)

        inflight = st.get("inflight")
        if isinstance(inflight, dict) and inflight.get("stage") in STAGES:
            stage = inflight["stage"]
            count = int(st["interruptions"].get(stage, 0)) + 1
            st["interruptions"][stage] = count
            st["inflight"] = None
            self.log.event(logging.WARNING, f"stage {stage} was interrupted (worker died; {count} so far)")
            if count > MAX_INTERRUPTIONS:
                self.fail(stage, f"The worker was interrupted {count} times during this stage")
                return
        if recheck or st["status"] == STATUS_WAITING_DUMP:
            st["pending_callbacks"] = [c for c in st.get("pending_callbacks") or []
                                       if c.get("event") != "waiting-dump"]
            st["announced_stage"] = None
            st["next_check"] = None
        st.update(status=STATUS_RUNNING, next_try=None, waiting_for=None)
        self.w.save_state(st)

        stages = {
            "resolve": self.stage_resolve,
            "prepare": self.stage_prepare,
            "dump": self.stage_dump,
            "pages": self.stage_pages,
            "images": self.stage_images,
            "upload": self.stage_upload,
            "finalize": self.stage_finalize,
        }
        while True:
            stage = Worker._next_stage(st)
            st["stage"] = stage
            if st.get("announced_stage") != stage:
                self.log.event(logging.INFO, f"entering stage {stage}")
                self.w.notify(st, "stage", stage=stage)
                st["announced_stage"] = stage
            st["inflight"] = {"stage": stage, "pid": os.getpid(), "started_at": iso(self.w.clock())}
            self.w.save_state(st)
            try:
                result = stages[stage]()
            except StageError as e:
                st["inflight"] = None
                self.stage_failed(stage, e)
                return
            except WorkerInterrupted:
                st["inflight"] = None
                self.w.save_state(st)
                raise
            except Exception as e:
                LOG.exception(f"import {self.id}: unexpected error in stage {stage}")
                st["inflight"] = None
                self.stage_failed(stage, StageError(f"Internal worker error: {type(e).__name__}: {clean_text(e, 300)}"))
                return
            st["inflight"] = None

            if result == FINISHED:
                return
            if result == WAITING:
                self.w.save_state(st)
                return
            if isinstance(result, Deferral):
                self.defer(result)
                return
            if isinstance(result, Rewind):
                self.log.event(logging.WARNING, f"going back to stage {result.stage}: {result.reason}")
                index = STAGES.index(result.stage)
                st["completed"] = [s for s in st["completed"] if STAGES.index(s) < index]
                self.w.save_state(st)
                continue
            if stage not in st["completed"]:
                st["completed"].append(stage)
            st["error"] = None
            self.w.save_state(st)
            self.w.flush_progress(st)

    def stage_failed(self, stage: str, err: StageError) -> None:
        st = self.st
        attempts = int(st["attempts"].get(stage, 0)) + 1
        st["attempts"][stage] = attempts
        message = clean_text(err, 1000)
        st["error"] = message
        if err.permanent or attempts >= self.cfg.max_stage_attempts:
            self.fail(stage, message)
            return
        delay = STAGE_BACKOFF[min(attempts - 1, len(STAGE_BACKOFF) - 1)]
        retry_at = self.w.clock() + timedelta(seconds=delay)
        st.update(status=STATUS_RUNNING, next_try=iso(retry_at), waiting_for=None)
        self.w.save_state(st)
        self.log.event(logging.WARNING, f"stage {stage} failed (attempt {attempts}/"
                                        f"{self.cfg.max_stage_attempts}): {message}; retrying at {iso(retry_at)}")

    def fail(self, stage: str, message: str) -> None:
        st = self.st
        now = self.w.clock()
        expire = now + timedelta(days=self.cfg.failed_retention_days)
        message = clean_text(message, 1000)
        st.update(status=STATUS_FAILED, stage=stage, failed_at=iso(now), files_expire=iso(expire),
                  error=message, next_try=None, inflight=None, waiting_for=None, pending_progress=None)
        self.log.event(logging.ERROR, f"failed in stage {stage}: {message} (files kept until {iso(expire)})")
        self.w.queue_callback(st, "failed", stage=stage, message=message, data={"files_expire": iso(expire)})
        self.w.flush_callbacks(st, force=True)

    def defer(self, deferral: Deferral) -> None:
        st = self.st
        retry_at = self.w.clock() + timedelta(seconds=deferral.seconds)
        st.update(status=STATUS_RUNNING, next_try=iso(retry_at), waiting_for="disk")
        self.w.save_state(st)
        self.log.event(logging.INFO, f"{deferral.message or 'deferred'}; trying again at {iso(retry_at)}")
        if deferral.message:
            self.w.progress(st, {**deferral.data, "next_try": iso(retry_at)}, deferral.message)

    def free_bytes(self) -> int:
        return shutil.disk_usage(self.cfg.spool_dir).free

    def need_disk(self, needed: int, what: str) -> Optional[Deferral]:
        free = self.free_bytes()
        if free >= needed:
            return None
        self.log.event(logging.WARNING, f"{what} needs {human_bytes(needed)} free, "
                                        f"only {human_bytes(free)} available")
        return Deferral(DISK_RETRY, "Waiting for disk space",
                        {"disk_free_bytes": free, "disk_needed_bytes": needed})

    def low_disk(self) -> Deferral:
        free = self.free_bytes()
        self.log.event(logging.WARNING, f"paused: only {human_bytes(free)} free "
                                        f"(floor {human_bytes(self.cfg.min_free_bytes)})")
        return Deferral(DISK_RETRY, "Paused: low disk space",
                        {"disk_free_bytes": free, "disk_min_free_bytes": self.cfg.min_free_bytes})

    def run_tool(self, cmd: Sequence[str], *, label: str, network: bool = False,
                 line_handler: Optional[Callable[[str], None]] = None,
                 poll: Optional[Callable[[], Optional[str]]] = None,
                 output_file: Optional[Path] = None,
                 stderr_path: Optional[Path] = None) -> ToolResult:
        """Run a long tool with output going to the import log (or a file in
        the work dir for the chatty ones), housekeeping while it runs."""
        self.log.info(f"running: {shlex.join(cmd)}")
        sink = open(output_file, "a", encoding="utf-8") if output_file else None
        lock = threading.Lock()

        def on_line(line: str) -> None:
            if sink:
                with lock:
                    sink.write(line + "\n")
            else:
                self.log.tool(label, line)
            if line_handler:
                line_handler(line)

        def on_poll() -> Optional[str]:
            self.w.maybe_housekeep()
            self.w.flush_progress(self.st)
            return poll() if poll else None

        try:
            result = run_streaming(cmd, env=self.w.child_env(self.tmp, network=network), cwd=self.dir,
                                   on_line=on_line, on_poll=on_poll, pass_fds=self.w.child_fds,
                                   stderr_path=stderr_path)
        finally:
            if sink:
                sink.close()
        self.log.info(f"{label} exited with {result.returncode}"
                      + (f" (terminated: {result.terminated})" if result.terminated else ""))
        if result.returncode != 0 and output_file:
            for line in result.tail[-20:]:
                self.log.tool(label, line)
        return result

    def mw_tool(self, script: str, *args: str, label: Optional[str] = None,
                **kwargs: Any) -> ToolResult:
        cmd = self.w.mw.command(script, self.manifest.target_wiki, *args)
        return self.run_tool(cmd, label=label or script, **kwargs)

    def require_success(self, result: ToolResult, what: str) -> None:
        if result.returncode != 0:
            detail = result.last_line()
            raise StageError(f"{what} exited with {result.returncode}" + (f": {detail}" if detail else ""))

    def upload_user(self) -> str:
        prepared = self.st["stage_data"].get("prepare") or {}
        return prepared.get("upload_user") or self.manifest.upload_user

    def stage_resolve(self) -> None:
        params = {
            "action": "query",
            "meta": "siteinfo",
            "siprop": "general|namespaces|statistics|extensions|rightsinfo",
            "format": "json",
            "formatversion": "2",
        }
        data = self.w.http.get_json(self.manifest.source.api_url, params)
        query = data.get("query") if isinstance(data, dict) else None
        general = query.get("general") if isinstance(query, dict) else None
        if not isinstance(general, dict):
            raise StageError("Fandom's siteinfo response has no query.general")
        statistics = query.get("statistics") if isinstance(query.get("statistics"), dict) else {}
        rights = query.get("rightsinfo") if isinstance(query.get("rightsinfo"), dict) else {}
        wikiid = general.get("wikiid")
        if not isinstance(wikiid, str) or not DBNAME_RE.fullmatch(wikiid):
            raise StageError(f"Fandom reported an unusable wiki id {clean_text(repr(wikiid), 80)}",
                             permanent=True)
        write_json_atomic(self.dir / "siteinfo.json", data)
        info = {
            "fandom_wikiid": wikiid,
            "fandom_sitename": clean_text(general.get("sitename") or "", 255),
            "fandom_pages": statistics.get("pages") if is_int(statistics.get("pages")) else None,
            "fandom_files": statistics.get("images") if is_int(statistics.get("images")) else None,
            "license": clean_text(rights.get("text") or "", 255) or None,
        }
        self.st["summary"].update(info)
        self.w.save_state(self.st)
        self.log.event(logging.INFO, f"resolved {self.manifest.source.base_url}: wikiid {wikiid}, "
                                     f"{info['fandom_pages']} pages, {info['fandom_files']} files")
        self.w.progress(self.st, info)

    def stage_prepare(self) -> Optional[Rewind]:
        siteinfo = self.dir / "siteinfo.json"
        if not siteinfo.is_file():
            return Rewind("resolve", "siteinfo.json is missing")
        last_json: list[str] = []

        def on_line(line: str) -> None:
            if line.lstrip().startswith("{"):
                last_json[:] = [line.strip()]

        result = self.mw_tool("WikiOasisMagic:FandomImportPrepare", f"--siteinfo={siteinfo.resolve()}",
                              f"--upload-user={self.manifest.upload_user}", label="prepare",
                              line_handler=on_line, stderr_path=self.tmp / "prepare-stderr.log")
        self._log_file_tail(self.tmp / "prepare-stderr.log", "prepare(stderr)")
        self.require_success(result, "FandomImportPrepare")
        if not last_json:
            raise StageError("FandomImportPrepare printed no JSON result")
        try:
            prepared = parse_prepare_output(last_json[0])
        except ValueError as e:
            raise StageError(f"FandomImportPrepare returned unusable JSON: {clean_text(e, 200)}") from None
        self.st["stage_data"]["prepare"] = prepared
        summary = self.st["summary"]
        summary["enabled_extensions"] = prepared["enabled_extensions"]
        summary["created_namespaces"] = prepared["created_namespaces"]
        summary["prepare_warnings"] = prepared["warnings"]
        self.w.save_state(self.st)
        for warning in prepared["warnings"]:
            self.log.event(logging.WARNING, f"prepare: {warning}")
        if prepared["upload_user"] != self.manifest.upload_user:
            self.log.event(logging.INFO, f"files will be uploaded as {prepared['upload_user']!r}")
        self.w.progress(self.st, {"enabled_extensions": prepared["enabled_extensions"],
                                  "created_namespaces": prepared["created_namespaces"]})
        return None

    def _log_file_tail(self, path: Path, label: str, limit: int = 64 * 1024) -> None:
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - limit))
                text = f.read().decode("utf-8", "replace")
        except FileNotFoundError:
            return
        for line in text.splitlines():
            if line.strip():
                self.log.tool(label, line)

    def check_dump(self, variant: str, url: str) -> DumpCheck:
        status, headers = self.w.http.head(url)
        check = DumpCheck(variant=variant, url=url, status=status)
        if headers is None:
            return check
        storage_class = headers.get("x-amz-storage-class")
        check.storage_class = clean_text(storage_class, 40) if storage_class else None
        restore = headers.get("x-amz-restore") or ""
        check.restored = 'ongoing-request="false"' in restore
        check.last_modified = _http_date_to_iso(headers.get("Last-Modified"))
        length = headers.get("Content-Length")
        check.content_length = int(length) if length and length.isdigit() else None
        md5 = (headers.get("x-amz-meta-md5") or "").strip().lower()
        check.md5 = md5 if MD5_RE.fullmatch(md5) else None
        etag = headers.get("ETag")
        check.etag = clean_text(etag, 200) if etag else None
        return check

    def stage_dump(self) -> Any:
        """Find a usable dump on S3 and download it to dump.xml.7z.

        A dump.xml.7z matching the recorded size was downloaded before a
        crash that lost only the state save, so it is kept. A .part file from
        a different object (the other variant, or a regenerated dump) cannot
        be resumed and is deleted.
        """
        st = self.st
        sd = st["stage_data"].setdefault("dump", {})
        wikiid = st["summary"].get("fandom_wikiid")
        if not isinstance(wikiid, str) or not DBNAME_RE.fullmatch(wikiid):
            raise StageError("no valid Fandom wiki id was recorded", permanent=True)
        dump_file = self.dir / DUMP_FILE
        part = self.dir / (DUMP_FILE + ".part")
        if sd.get("complete") and dump_file.is_file() and dump_file.stat().st_size == sd.get("bytes"):
            return None

        prefer = self.manifest.prefer_full_history
        if prefer is None:
            prefer = self.cfg.prefer_full_history
        checks = [self.check_dump(variant, url) for variant, url in dump_candidates(wikiid, prefer)]
        for check in checks:
            self.log.info(f"dump {check.variant}: {check.describe()}, last modified {check.last_modified}")
        usable = next((c for c in checks if c.usable), None)
        if usable is None:
            return self.wait_for_dump(checks)
        if usable.content_length is None:
            raise StageError("S3 did not report the dump's size")

        if sd.get("url") != usable.url or sd.get("etag") != usable.etag:
            self.w.rmtree(part, self.log)
        sd.update(variant=usable.variant, url=usable.url, bytes=usable.content_length,
                  md5=usable.md5, etag=usable.etag, last_modified=usable.last_modified, complete=False)
        self.w.save_state(st)

        have = part.stat().st_size if part.is_file() else 0
        deferral = self.need_disk(usable.content_length - have + self.cfg.disk_headroom_bytes, "dump download")
        if deferral:
            return deferral
        self.log.event(logging.INFO, f"downloading {usable.variant} dump ({human_bytes(usable.content_length)}"
                                     f", last modified {usable.last_modified})")
        outcome = self.download(usable, part)
        if outcome is not None:
            return outcome
        size = part.stat().st_size
        if size != usable.content_length:
            raise StageError(f"dump size is {size}, S3 said {usable.content_length}")
        if usable.md5:
            digest = hashlib.md5(usedforsecurity=False)
            with open(part, "rb") as f:
                while chunk := f.read(DOWNLOAD_CHUNK):
                    digest.update(chunk)
            if digest.hexdigest() != usable.md5:
                self.w.rmtree(part, self.log)
                raise StageError("dump MD5 does not match x-amz-meta-md5; deleted, will download again")
        os.replace(part, dump_file)
        sd["complete"] = True
        st["summary"].update(dump_variant=usable.variant, dump_url=usable.url,
                             dump_date=usable.last_modified, dump_bytes=usable.content_length)
        self.w.save_state(st)
        self.w.progress(st, {"dump_variant": usable.variant, "dump_date": usable.last_modified,
                             "dump_bytes": usable.content_length})
        return None

    def wait_for_dump(self, checks: list[DumpCheck]) -> str:
        st = self.st
        now = self.w.clock()
        since = parse_iso(st.get("waiting_since")) or now
        deadline = since + timedelta(days=self.cfg.dump_max_wait_days)
        details = "; ".join(f"{c.variant}: {c.describe()}" for c in checks)
        if now >= deadline:
            raise StageError(
                f"No usable Fandom XML dump appeared within {self.cfg.dump_max_wait_days:g} days "
                f"({details}). Ask Fandom to generate a new dump, then retry.", permanent=True)
        next_check = min(now + timedelta(hours=self.cfg.dump_recheck_hours), deadline)
        st.update(status=STATUS_WAITING_DUMP, waiting_since=iso(since), next_check=iso(next_check),
                  waiting_for="dump", next_try=None, announced_stage=None, inflight=None)
        self.log.event(logging.INFO, f"no usable dump ({details}); checking again at {iso(next_check)}")
        self.w.queue_callback(st, "waiting-dump", data={
            "next_check": iso(next_check),
            "waiting_since": iso(since),
            "dumps": [c.to_callback() for c in checks],
        })
        self.w.flush_callbacks(st, force=True)
        return WAITING

    def download(self, check: DumpCheck, part: Path) -> Optional[Deferral]:
        """Download `check.url` into `part`, resuming with Range requests.

        If-Range makes S3 send the whole object again if it changed. A 416
        means the partial file no longer fits the object, so it starts over.
        A full disk (ENOSPC) or free space below the floor pauses the stage
        instead of failing it.
        """
        total = check.content_length or 0
        failures = 0
        last_error = ""
        last_tick = time.monotonic()
        while True:
            have = part.stat().st_size if part.is_file() else 0
            if have == total:
                return None
            if have > total:
                self.w.rmtree(part, self.log)
                have = 0
            headers: dict[str, str] = {}
            if have:
                headers["Range"] = f"bytes={have}-"
                if check.etag:
                    headers["If-Range"] = check.etag
            try:
                with self.w.http.open(check.url, headers=headers, timeout=DOWNLOAD_TIMEOUT) as resp:
                    if resp.status == 206:
                        content_range = resp.headers.get("Content-Range") or ""
                        if not content_range.startswith(f"bytes {have}-"):
                            raise StageError(f"unexpected Content-Range {clean_text(content_range, 80)}")
                        mode = "ab"
                    elif resp.status == 200:
                        mode, have = "wb", 0
                    else:
                        raise StageError(f"unexpected HTTP {resp.status} while downloading the dump")
                    with open(part, mode) as f:
                        while True:
                            chunk = resp.read(DOWNLOAD_CHUNK)
                            if not chunk:
                                break
                            f.write(chunk)
                            have += len(chunk)
                            if have > total:
                                raise StageError("the dump is larger than S3 reported")
                            if time.monotonic() - last_tick >= POLL_INTERVAL:
                                last_tick = time.monotonic()
                                if self.free_bytes() < self.cfg.min_free_bytes:
                                    return self.low_disk()
                                self.w.progress(self.st, {"dump_bytes_downloaded": have, "dump_bytes": total})
                if have != total:
                    failures += 1
                    last_error = f"connection closed at {have} of {total} bytes"
                else:
                    continue
            except urllib.error.HTTPError as e:
                status = e.code
                e.close()
                if status == 416:
                    self.w.rmtree(part, self.log)
                elif status in (403, 404):
                    raise StageError(f"dump download refused with HTTP {status} "
                                     f"(it may have moved to cold storage)") from None
                failures += 1
                last_error = f"HTTP {status}"
            except OSError as e:
                if getattr(e, "errno", None) == errno.ENOSPC:
                    return self.low_disk()
                failures += 1
                last_error = clean_text(e, 200)
            except http.client.HTTPException as e:
                failures += 1
                last_error = clean_text(e, 200)
            if failures > self.cfg.retries:
                raise StageError(f"dump download failed {failures} times: {last_error}")
            self.log.warning(f"dump download interrupted ({last_error}); resuming")
            time.sleep(min(5 * 2 ** failures, 300))

    def namespaces(self) -> Optional[list[int]]:
        prepared = self.st["stage_data"].get("prepare") or {}
        namespaces = prepared.get("namespaces")
        if isinstance(namespaces, list) and namespaces and all(is_int(n) for n in namespaces):
            return namespaces
        return None

    def stage_pages(self) -> Any:
        """Filter the dump, import it, rebuild recent changes and counts.

        The dump is deleted as soon as the filtered copy is complete and
        verified, and the filtered copy as soon as it is imported. Each step
        is recorded, so a resumed stage skips what is already done.
        """
        st = self.st
        sd = st["stage_data"].setdefault("pages", {})
        dump_file = self.dir / DUMP_FILE
        gz = self.dir / PAGES_FILE
        namespaces = self.namespaces()
        if namespaces is None:
            return Rewind("prepare", "the namespace list from FandomImportPrepare is missing")

        if not sd.get("imported") and not (sd.get("filtered") and gz.is_file()):
            if not dump_file.is_file():
                st["stage_data"].pop("pages", None)
                st["stage_data"].pop("dump", None)
                return Rewind("dump", "the downloaded dump is missing")
            outcome = self.filter_dump(dump_file, gz, namespaces)
            if isinstance(outcome, Deferral):
                return outcome
            sd.update(filtered=True, pages_kept=outcome.pages_kept, pages_skipped=outcome.pages_skipped,
                      skipped_namespaces=outcome.skipped_namespaces)
            st["summary"].update(pages_kept=outcome.pages_kept, pages_skipped=outcome.pages_skipped,
                                 skipped_namespaces=outcome.skipped_namespaces)
            self.w.save_state(st)
            self.log.event(logging.INFO, f"filtered dump: {outcome.pages_kept} pages kept, "
                                         f"{outcome.pages_skipped} skipped {outcome.skipped_namespaces}")
        if dump_file.exists():
            self.w.rmtree(dump_file, self.log)

        if not sd.get("imported"):
            imported = {"pages": 0}
            reported = {"pages": -1}

            def on_line(line: str) -> None:
                match = IMPORTDUMP_REPORT_RE.match(line)
                if match:
                    imported["pages"] = int(match.group(1))

            def poll() -> None:
                if imported["pages"] != reported["pages"]:
                    reported["pages"] = imported["pages"]
                    self.w.progress(st, {"pages_imported": imported["pages"]})

            result = self.mw_tool("importDump", f"--username-prefix={self.manifest.username_prefix}",
                                  "--no-local-users", "--report=1000", str(gz.resolve()),
                                  line_handler=on_line, poll=poll)
            self.require_success(result, "importDump")
            sd["imported"] = True
            self.w.save_state(st)

        if not sd.get("recounted"):
            self.require_success(self.mw_tool("rebuildrecentchanges"), "rebuildrecentchanges")
            self.require_success(self.mw_tool("initSiteStats", "--update"), "initSiteStats")
            sd["recounted"] = True
            self.w.save_state(st)

        if gz.exists():
            self.w.rmtree(gz, self.log)
        self.w.progress(st, {"pages_kept": sd.get("pages_kept", 0), "pages_skipped": sd.get("pages_skipped", 0),
                             "skipped_namespaces": sd.get("skipped_namespaces", {})})
        return None

    def estimate_xml_size(self, dump_file: Path) -> Optional[int]:
        try:
            proc = subprocess.run(
                [self.cfg.sevenzip, "l", "-slt", str(dump_file)], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=self.w.child_env(self.tmp),
                cwd=str(self.dir), timeout=600, pass_fds=self.w.child_fds,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            self.log.warning(f"could not list the dump: {clean_text(e, 200)}")
            return None
        if proc.returncode != 0:
            self.log.warning(f"7z l exited with {proc.returncode}")
            return None
        return parse_7z_listing_size(proc.stdout.decode("utf-8", "replace"))

    def filter_dump(self, dump_file: Path, gz: Path, namespaces: list[int]) -> Any:
        """7z e -so | namespace filter | gzip -> pages.xml.gz (verified)."""
        estimate = self.estimate_xml_size(dump_file)
        if estimate:
            deferral = self.need_disk(estimate // GZIP_RATIO_ESTIMATE + self.cfg.disk_headroom_bytes,
                                      "namespace filter")
            if deferral:
                return deferral
        tmp_gz = self.dir / (PAGES_FILE + ".tmp")
        stderr_path = self.tmp / "7z-stderr.log"
        keep = frozenset(namespaces)
        last_check = [time.monotonic()]

        def check_disk() -> None:
            if time.monotonic() - last_check[0] < POLL_INTERVAL:
                return
            last_check[0] = time.monotonic()
            if self.free_bytes() < self.cfg.min_free_bytes:
                raise LowDiskSpace()

        self.log.info(f"filtering dump, keeping namespaces {sorted(keep)}")
        with open(stderr_path, "wb") as stderr_file:
            proc = subprocess.Popen(
                [self.cfg.sevenzip, "e", "-so", "-bd", str(dump_file)], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=stderr_file, env=self.w.child_env(self.tmp),
                cwd=str(self.dir), pass_fds=self.w.child_fds, start_new_session=True,
            )
        assert proc.stdout is not None
        reader = io.TextIOWrapper(proc.stdout, encoding="utf-8", errors="surrogateescape", newline="\n")
        try:
            with gzip.open(tmp_gz, "wt", compresslevel=GZIP_LEVEL, encoding="utf-8",
                           errors="surrogateescape", newline="\n") as out:
                stats = filter_dump_lines(reader, out.write, keep, check=check_disk)
            returncode = proc.wait()
        except LowDiskSpace:
            terminate_process_group(proc)
            self.w.rmtree(tmp_gz, self.log)
            return self.low_disk()
        except DumpFormatError as e:
            terminate_process_group(proc)
            self.w.rmtree(tmp_gz, self.log)
            raise StageError(f"the dump is not usable XML: {e}") from None
        except BaseException:
            terminate_process_group(proc)
            self.w.rmtree(tmp_gz, self.log)
            raise
        finally:
            if proc.poll() is None:
                terminate_process_group(proc)
            reader.close()
        self._log_file_tail(stderr_path, "7z")
        if returncode != 0:
            self.w.rmtree(tmp_gz, self.log)
            raise StageError(f"7z exited with {returncode} while extracting the dump")
        if not stats.saw_footer:
            self.w.rmtree(tmp_gz, self.log)
            raise StageError("the dump ends without </mediawiki>; it is probably truncated")
        try:
            verify_gzip_xml(tmp_gz)
        except (OSError, EOFError, ValueError) as e:
            self.w.rmtree(tmp_gz, self.log)
            raise StageError(f"the filtered XML did not verify: {clean_text(e, 200)}") from None
        os.replace(tmp_gz, gz)
        return stats

    def list_source_files(self) -> tuple[int, int]:
        """(count, bytes) of the source wiki's files, via list=allimages."""
        params: dict[str, str] = {"action": "query", "list": "allimages", "aiprop": "size",
                                  "ailimit": "500", "format": "json", "formatversion": "2"}
        total = 0
        size = 0
        requests = 0
        while True:
            if requests:
                time.sleep(self.cfg.image_delay)
            data = self.w.http.get_json(self.manifest.source.api_url, params)
            requests += 1
            query = data.get("query") if isinstance(data, dict) else None
            images = query.get("allimages") if isinstance(query, dict) else None
            if not isinstance(images, list):
                raise StageError("list=allimages response has no query.allimages")
            for image in images:
                total += 1
                if isinstance(image, dict) and is_int(image.get("size")):
                    size += image["size"]
            cont = data.get("continue")
            if not isinstance(cont, dict):
                return total, size
            for key, value in cont.items():
                if isinstance(key, str) and isinstance(value, (str, int)):
                    params[key] = str(value)
            if requests % 20 == 0:
                self.w.maybe_housekeep()

    def stage_images(self) -> Any:
        """List the source files, then download them with wikiteam3.

        wikiteam3 mkdir()s --path and then writes config.json into it, so a
        crawl dir without config.json is from a run that died in between: it
        can neither be resumed (no config) nor started in (wikiteam3 would ask
        on stdin), and is deleted. --force skips wikiteam3's "already on the
        Internet Archive" check, which would exit 88 for any wiki archived in
        the last year.
        """
        st = self.st
        sd = st["stage_data"].setdefault("images", {})
        if "total" not in sd:
            total, nbytes = self.list_source_files()
            sd.update(total=total, bytes=nbytes)
            st["summary"].update(images_total=total, images_bytes_total=nbytes)
            self.w.save_state(st)
            self.log.event(logging.INFO, f"source wiki has {total} files ({human_bytes(nbytes)})")
            self.w.progress(st, {"images_total": total, "images_bytes_total": nbytes})
        crawl = self.dir / CRAWL_DIR
        if sd["total"] == 0:
            st["summary"]["images_fetched"] = 0
            return None

        on_disk = tree_size(crawl) if crawl.is_dir() else 0
        deferral = self.need_disk(max(0, sd["bytes"] - on_disk) + self.cfg.disk_headroom_bytes, "image download")
        if deferral:
            return deferral

        config_file = crawl / "config.json"
        if crawl.exists() and not config_file.is_file():
            self.w.rmtree(crawl, self.log)
        resume = config_file.is_file()
        src = self.manifest.source
        cmd = [
            self.cfg.wikiteam3,
            "--api", src.api_url,
            "--index", src.index_url,
            "--images",
            "--path", str(crawl),
            "--delay", f"{self.cfg.image_delay:g}",
            "--retries", str(self.cfg.retries),
            "--user-agent", self.cfg.user_agent,
            "--api_chunksize", str(WIKITEAM3_CHUNKSIZE),
            "--force",
        ]
        if resume:
            cmd.append("--resume")
        fetched = {"count": -1}

        def poll() -> Optional[str]:
            count = sum(count_files(crawl / d) for d in IMAGE_DIRS)
            if count != fetched["count"]:
                fetched["count"] = count
                self.w.progress(st, {"images_fetched": count, "images_total": sd["total"]})
            if self.free_bytes() < self.cfg.min_free_bytes:
                return "low disk space"
            return None

        result = self.run_tool(cmd, label="wikiteam3", network=True, poll=poll,
                               output_file=self.dir / "wikiteam3.log")
        st["summary"]["images_fetched"] = sum(count_files(crawl / d) for d in IMAGE_DIRS)
        self.w.save_state(st)
        if result.terminated:
            return self.low_disk()
        if result.returncode != 0:
            raise StageError(self.describe_wikiteam3_exit(result))
        self.log.event(logging.INFO, f"wikiteam3 finished: {st['summary']['images_fetched']} files on disk")
        return None

    @staticmethod
    def describe_wikiteam3_exit(result: ToolResult) -> str:
        known = {
            11: "wikiteam3 could not verify index.php",
            20: "the wiki's robots.txt disallows wikiteam3",
            88: "wikiteam3 refused because of an existing Internet Archive item",
        }
        text = known.get(result.returncode, f"wikiteam3 exited with {result.returncode}")
        detail = result.last_line()
        return text + (f": {detail}" if detail else "")

    def stage_upload(self) -> None:
        """importImages images/ then images_mismatch/, deleting each when done.

        Fandom recompresses files, so many good ones land in images_mismatch.
        A directory's counts are recorded before it is deleted, so a crash in
        between cannot lose them.
        """
        st = self.st
        sd = st["stage_data"].setdefault("upload", {})
        dirs_done: dict[str, Any] = sd.setdefault("dirs", {})
        crawl = self.dir / CRAWL_DIR
        user = self.upload_user()
        for name in IMAGE_DIRS:
            path = crawl / name
            if name not in dirs_done:
                files = count_files(path) if path.is_dir() else 0
                dirs_done[name] = self.import_images_dir(path, name, files, user) if files else {"files": 0}
                self.w.save_state(st)
            if path.exists():
                self.w.rmtree(path, self.log)

        totals = {"images_added": 0, "images_skipped": 0, "images_failed": 0,
                  "images_overwritten": 0, "images_unsupported": 0}
        failed_files: list[str] = []
        for result in dirs_done.values():
            totals["images_added"] += int(result.get("added", 0))
            totals["images_skipped"] += int(result.get("skipped", 0))
            totals["images_failed"] += int(result.get("failed", 0))
            totals["images_overwritten"] += int(result.get("overwritten", 0))
            totals["images_unsupported"] += int(result.get("unsupported", 0))
            failed_files.extend(result.get("failed_files", []))
        st["summary"].update(totals, failed_files=failed_files[:FAILED_FILES_KEEP])
        if crawl.exists():
            self.w.rmtree(crawl, self.log)
        self.w.save_state(st)
        self.log.event(logging.INFO, f"upload: {totals}")
        self.w.progress(st, totals)

    def import_images_dir(self, path: Path, name: str, files: int, user: str) -> dict[str, Any]:
        """Run importImages on one directory and return its counts.

        importImages exits 1 when any file failed, or when no file had an
        allowed extension; both are results, not a broken stage. Files whose
        extension the target wiki does not allow are not even "found", so
        they are counted as `unsupported` to make the summary add up.
        """
        parser = ImportImagesParser()
        reported = {"added": -1}

        def poll() -> None:
            if parser.done_lines != reported["added"]:
                reported["added"] = parser.done_lines
                self.w.progress(self.st, {"images_uploaded": parser.done_lines})

        summary = self.manifest.summary
        result = self.mw_tool("importImages", "--search-recursively", f"--user={user}",
                              f"--summary={summary}", f"--comment={summary}", str(path.resolve()),
                              label=f"importImages[{name}]", line_handler=parser.feed, poll=poll,
                              output_file=self.dir / f"importImages-{name}.log")
        if result.returncode != 0 and not (result.returncode == 1 and (parser.has_summary or parser.no_files)):
            raise StageError(f"importImages ({name}) exited with {result.returncode}"
                             + (f": {result.last_line()}" if result.last_line() else ""))
        counts = parser.result()
        counts["unsupported"] = max(0, files - counts["found"]) if counts["found"] or parser.no_files else 0
        counts["files"] = files
        self.log.event(logging.INFO, f"importImages {name}: {files} files, added {counts['added']}, "
                                     f"skipped {counts['skipped']}, failed {counts['failed']}")
        for failed in counts["failed_files"]:
            self.log.warning(f"importImages {name}: failed: {failed}")
        return counts

    def stage_finalize(self) -> str:
        self.require_success(self.mw_tool("initSiteStats", "--update"), "initSiteStats")
        st = self.st
        now = self.w.clock()
        summary = dict(st["summary"])
        summary["started_at"] = st.get("created_at")
        summary["finished_at"] = iso(now)
        st["status"] = STATUS_DONE
        st["inflight"] = None
        st["pending_progress"] = None
        if "finalize" not in st["completed"]:
            st["completed"].append("finalize")
        self.w.save_state(st)
        freed = self.w.purge_work_files(self.id)
        self.log.event(logging.INFO, f"import finished; {human_bytes(freed)} of working files deleted")
        self.w.queue_callback(st, "done", data=summary)
        self.w.flush_callbacks(st, force=True)
        self.w.finish_tombstone(st)
        return FINISHED


_interrupted = False


def _on_signal(signum: int, _frame: Any) -> None:
    """Turn the first SIGTERM/SIGINT into WorkerInterrupted; ignore repeats so
    the cleanup that is already unwinding can finish."""
    global _interrupted
    if _interrupted:
        return
    _interrupted = True
    raise WorkerInterrupted(signal.Signals(signum).name)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point. umask 027: the spool is www-data's and nothing in it
    needs to be world-readable."""
    parser = argparse.ArgumentParser(description="WikiOasis Fandom import worker")
    parser.add_argument("--config", required=True, type=Path, help="path to config.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="process discards, then work on one import (cron, every minute)")
    sub.add_parser("janitor", help="expire old logs and stray files (cron, daily)")
    args = parser.parse_args(argv)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_utc_formatter())
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    os.umask(0o027)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _on_signal)

    cfg = Config.load(args.config)
    worker = Worker(cfg)
    try:
        if args.command == "run":
            return worker.cmd_run()
        return worker.cmd_janitor()
    except WorkerInterrupted as e:
        LOG.warning(f"interrupted by {e}; state saved, the next run resumes")
        return 1
    except Exception:
        LOG.exception("worker failed")
        return 1
    finally:
        worker.close_logs()


if __name__ == "__main__":
    sys.exit(main())
