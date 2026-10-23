#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import http.cookiejar
import json
import logging
import os
import re
import signal
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("sal-server")

REF_RE = re.compile(r"(?<![\w/#.-])([TDP][1-9][0-9]*|r[A-Z]+[0-9a-f]{7,40})(?![\w-])")
HEADING_RE = re.compile(r"^==\s*(\d{4}-\d{2}-\d{2})\s*==[ \t]*$", re.M)
ENTRY_LINE_RE = re.compile(r"^\* (\d{2}:\d{2}) .*$", re.M)
SECTION_END_RE = re.compile(r"^=", re.M)
USER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,254}$")
RELATIVE_RE = re.compile(r"^(\d+)\s*([mhdw])$")
UNITS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
MAX_BODY = 65536
TRANSIENT_WIKI_CODES = {
    "ratelimited",
    "readonly",
    "maxlag",
    "editconflict",
    "badtoken",
    "assertuserfailed",
    "assertbotfailed",
    "articleexists",
}

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS sal_entries (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      created_at DATETIME(6) NOT NULL,
      updated_at DATETIME(6) NULL,
      user VARCHAR(64) NOT NULL,
      host VARCHAR(255) NOT NULL,
      minion VARCHAR(255) NOT NULL,
      message TEXT NOT NULL,
      is_command TINYINT(1) NOT NULL DEFAULT 0,
      exit_code INT NULL,
      deleted TINYINT(1) NOT NULL DEFAULT 0,
      wiki_state VARCHAR(16) NOT NULL,
      wiki_op VARCHAR(16) NOT NULL DEFAULT 'insert',
      wiki_line TEXT NULL,
      wiki_revid BIGINT UNSIGNED NULL,
      wiki_attempts INT NOT NULL DEFAULT 0,
      wiki_next_at DATETIME(6) NOT NULL,
      wiki_error TEXT NULL,
      phorge_state VARCHAR(16) NOT NULL,
      phorge_refs VARCHAR(1024) NULL,
      phorge_attempts INT NOT NULL DEFAULT 0,
      phorge_next_at DATETIME(6) NOT NULL,
      phorge_error TEXT NULL,
      PRIMARY KEY (id),
      KEY created_at (created_at),
      KEY user_created (user, created_at),
      KEY host_created (host, created_at),
      KEY wiki_queue (wiki_state, wiki_next_at),
      KEY phorge_queue (phorge_state, phorge_next_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS sal_history (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      entry_id BIGINT UNSIGNED NOT NULL,
      at DATETIME(6) NOT NULL,
      actor_user VARCHAR(64) NOT NULL,
      actor_host VARCHAR(255) NOT NULL,
      action VARCHAR(16) NOT NULL,
      old_message TEXT NULL,
      new_message TEXT NULL,
      PRIMARY KEY (id),
      KEY entry_id (entry_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def truthy(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class Config:
    def __init__(self, env):
        self.listen_host = env.get("SAL_LISTEN_HOST", "127.0.0.1")
        self.listen_port = int(env.get("SAL_LISTEN_PORT", "8740"))
        self.secret = env.get("SAL_SECRET", "")
        self.db = {
            "host": env.get("SAL_DB_HOST", "127.0.0.1"),
            "port": int(env.get("SAL_DB_PORT", "3306")),
            "database": env.get("SAL_DB_NAME", "sal"),
            "user": env.get("SAL_DB_USER", "sal"),
            "password": env.get("SAL_DB_PASSWORD", ""),
        }
        self.max_message = int(env.get("SAL_MAX_MESSAGE", "2000"))
        self.poll_interval = float(env.get("SAL_POLL_INTERVAL", "5"))
        self.max_attempts = int(env.get("SAL_MAX_ATTEMPTS", "50"))
        self.user_agent = env.get(
            "SAL_USER_AGENT", "WikiOasis-SAL/1.0 (+https://meta.wikioasis.org/wiki/Tech:Server_admin_log)"
        )
        self.wiki_enabled = truthy(env.get("SAL_WIKI_ENABLED", "1"))
        self.wiki_api = env.get("SAL_WIKI_API", "https://meta.wikioasis.org/w/api.php")
        self.wiki_page = env.get("SAL_WIKI_PAGE", "Tech:Server admin log")
        self.wiki_page_url = env.get("SAL_WIKI_PAGE_URL") or (
            "https://meta.wikioasis.org/wiki/" + urllib.parse.quote(self.wiki_page.replace(" ", "_"))
        )
        self.wiki_user = env.get("SAL_WIKI_USER", "")
        self.wiki_password = env.get("SAL_WIKI_PASSWORD", "")
        self.phorge_enabled = truthy(env.get("SAL_PHORGE_ENABLED", "1"))
        self.phorge_base = env.get("SAL_PHORGE_BASE", "https://phorge.wikioasis.org").rstrip("/")
        self.phorge_hook = env.get("SAL_PHORGE_HOOK", self.phorge_base + "/sal/hook")
        self.phorge_token = env.get("SAL_PHORGE_TOKEN", "")


def host_token(secret: str, minion: str) -> str:
    return hashlib.sha256(f"{secret}:{minion}".encode()).hexdigest()


def verify_host(secret: str, minion: str, token: str) -> bool:
    if not secret or not minion or not token or not HOST_RE.match(minion):
        return False
    return hmac.compare_digest(host_token(secret, minion), token)


def short_host(minion: str) -> str:
    return minion.split(".", 1)[0]


def clean_message(text, limit: int) -> str:
    if not isinstance(text, str):
        raise ValueError("message must be a string")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError("message is empty")
    if len(text) > limit:
        raise ValueError(f"message is longer than {limit} characters")
    return text


def clean_user(user) -> str:
    if not isinstance(user, str) or not USER_RE.match(user):
        raise ValueError("user is missing or invalid")
    return user


def parse_when(value: str, now: datetime | None = None) -> datetime:
    now = now or utcnow()
    value = value.strip()
    match = RELATIVE_RE.match(value)
    if match:
        return now - timedelta(seconds=int(match.group(1)) * UNITS[match.group(2)])
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** min(attempts, 7), 3600))


def extract_refs(text: str) -> list[str]:
    seen = []
    for match in REF_RE.finditer(text):
        if match.group(1) not in seen:
            seen.append(match.group(1))
    return seen


def wiki_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nowiki(text: str) -> str:
    return f"<nowiki>{wiki_escape(text)}</nowiki>" if text else ""


def linkify(text: str, phorge_base: str) -> str:
    parts = []
    pos = 0
    for match in REF_RE.finditer(text):
        parts.append(nowiki(text[pos : match.start()]))
        ref = match.group(1)
        parts.append(f"[{phorge_base}/{ref} {ref}]")
        pos = match.end()
    parts.append(nowiki(text[pos:]))
    return "".join(parts)


def render_line(entry: dict, phorge_base: str) -> str:
    stamp = entry["created_at"].strftime("%H:%M")
    if entry.get("is_command"):
        body = f"<code>{nowiki(entry['message'])}</code>"
        if entry.get("exit_code") not in (None, 0):
            body += f" (exit {entry['exit_code']})"
    else:
        body = linkify(entry["message"], phorge_base)
    return f"* {stamp} {entry['user']}@{entry['host']}: {body}"


def insert_line(text: str, day: str, hhmm: str, line: str) -> str:
    for heading in HEADING_RE.finditer(text):
        found = heading.group(1)
        if found == day:
            end_match = SECTION_END_RE.search(text, heading.end())
            end = end_match.start() if end_match else len(text)
            last = heading.end()
            for existing in ENTRY_LINE_RE.finditer(text, heading.end(), end):
                if existing.group(1) <= hhmm:
                    return text[: existing.start()] + line + "\n" + text[existing.start() :]
                last = existing.end()
            return text[:last] + "\n" + line + text[last:]
        if found < day:
            return text[: heading.start()] + f"== {day} ==\n{line}\n\n" + text[heading.start() :]
    body = text.rstrip("\n")
    separator = "\n\n" if body.strip() else ""
    return f"{body}{separator}== {day} ==\n{line}\n"


def replace_line(text: str, old: str, new: str) -> str | None:
    lines = text.split("\n")
    if old not in lines:
        return None
    lines[lines.index(old)] = new
    return "\n".join(lines)


def remove_line(text: str, old: str) -> str:
    lines = text.split("\n")
    if old not in lines:
        return text
    index = lines.index(old)
    del lines[index]
    if index > 0 and HEADING_RE.match(lines[index - 1]):
        following = lines[index] if index < len(lines) else ""
        if not following.startswith("* "):
            del lines[index - 1]
            if index - 1 < len(lines) and lines[index - 1] == "":
                del lines[index - 1]
    return "\n".join(lines)


def apply_wiki_op(text: str, entry: dict, phorge_base: str) -> tuple[str, str | None]:
    op = entry["wiki_op"]
    if op == "delete" or entry.get("deleted"):
        if entry.get("wiki_line"):
            return remove_line(text, entry["wiki_line"]), None
        return text, None
    line = render_line(entry, phorge_base)
    if op == "update" and entry.get("wiki_line"):
        replaced = replace_line(text, entry["wiki_line"], line)
        if replaced is not None:
            return replaced, line
    if line in text.split("\n"):
        return text, line
    day = entry["created_at"].strftime("%Y-%m-%d")
    return insert_line(text, day, entry["created_at"].strftime("%H:%M"), line), line


def edit_summary(entries: list[dict]) -> str:
    first = entries[0]
    if first["wiki_op"] == "delete" or first.get("deleted"):
        summary = f"SAL: remove #{first['id']}"
    elif first["wiki_op"] == "update":
        summary = f"SAL: edit #{first['id']}"
    else:
        summary = f"SAL: {first['user']}@{first['host']}: {first['message']}"
    if len(summary) > 200:
        summary = summary[:197] + "..."
    if len(entries) > 1:
        summary += f" (+{len(entries) - 1} more)"
    return summary


def phorge_payload(cfg: Config, row: dict) -> dict:
    message = row["message"]
    if row["is_command"]:
        message = f"`{message}`"
        if row["exit_code"] not in (None, 0):
            message += f" (exit {row['exit_code']})"
    return {
        "message": message,
        "user": row["user"],
        "channel": row["host"],
    }


def serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "created_at": iso(row["created_at"]),
        "updated_at": iso(row.get("updated_at")),
        "user": row["user"],
        "host": row["host"],
        "minion": row["minion"],
        "message": row["message"],
        "command": bool(row["is_command"]),
        "exit_code": row["exit_code"],
        "deleted": bool(row["deleted"]),
        "wiki": {
            "state": row["wiki_state"],
            "op": row["wiki_op"],
            "revid": row["wiki_revid"],
            "attempts": row["wiki_attempts"],
            "error": row["wiki_error"],
        },
        "phorge": {
            "state": row["phorge_state"],
            "refs": [r for r in (row["phorge_refs"] or "").split(",") if r],
            "attempts": row["phorge_attempts"],
            "error": row["phorge_error"],
        },
    }


class Database:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def connect(self):
        import pymysql
        import pymysql.cursors

        return pymysql.connect(
            host=self.cfg.db["host"],
            port=self.cfg.db["port"],
            user=self.cfg.db["user"],
            password=self.cfg.db["password"],
            database=self.cfg.db["database"],
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def run(self, sql: str, args=None, fetch: str | None = None):
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, args)
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
                return cur.lastrowid
        finally:
            conn.close()

    def ensure_schema(self):
        for statement in SCHEMA:
            self.run(statement)

    def get(self, entry_id: int):
        return self.run("SELECT * FROM sal_entries WHERE id = %s", (entry_id,), fetch="one")


class WikiError(Exception):
    def __init__(self, code: str, info: str = ""):
        super().__init__(f"{code}: {info}" if info else code)
        self.code = code

    @property
    def transient(self) -> bool:
        return self.code in TRANSIENT_WIKI_CODES or self.code.startswith("internal_api_error")


class Wiki:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.logged_in = False

    def _call(self, params: dict) -> dict:
        data = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"}).encode()
        request = urllib.request.Request(self.cfg.wiki_api, data=data, headers={"User-Agent": self.cfg.user_agent})
        with self.opener.open(request, timeout=30) as response:
            body = json.loads(response.read().decode())
        if "error" in body:
            raise WikiError(body["error"].get("code", "unknown"), body["error"].get("info", ""))
        return body

    def login(self):
        self.jar.clear()
        token = self._call({"action": "query", "meta": "tokens", "type": "login"})["query"]["tokens"]["logintoken"]
        result = self._call(
            {
                "action": "login",
                "lgname": self.cfg.wiki_user,
                "lgpassword": self.cfg.wiki_password,
                "lgtoken": token,
            }
        )["login"]
        if result.get("result") != "Success":
            raise WikiError("loginfailed", result.get("reason", result.get("result", "")))
        self.logged_in = True

    def _authed(self, params: dict) -> dict:
        if not self.logged_in:
            self.login()
        try:
            return self._call({**params, "assert": "user"})
        except WikiError as exc:
            if exc.code not in ("assertuserfailed", "assertbotfailed", "badtoken"):
                raise
            self.login()
            return self._call({**params, "assert": "user"})

    def fetch(self) -> dict:
        body = self._authed(
            {
                "action": "query",
                "prop": "revisions",
                "titles": self.cfg.wiki_page,
                "rvprop": "content|timestamp",
                "rvslots": "main",
                "meta": "tokens",
                "curtimestamp": "1",
            }
        )
        page = body["query"]["pages"][0]
        revisions = page.get("revisions") or []
        return {
            "text": revisions[0]["slots"]["main"]["content"] if revisions else "",
            "basetimestamp": revisions[0]["timestamp"] if revisions else None,
            "starttimestamp": body.get("curtimestamp"),
            "token": body["query"]["tokens"]["csrftoken"],
            "missing": bool(page.get("missing")),
        }

    def save(self, page: dict, text: str, summary: str):
        params = {
            "action": "edit",
            "title": self.cfg.wiki_page,
            "text": text,
            "summary": summary,
            "token": page["token"],
            "bot": "1",
        }
        if page["starttimestamp"]:
            params["starttimestamp"] = page["starttimestamp"]
        if page["missing"]:
            params["createonly"] = "1"
        elif page["basetimestamp"]:
            params["basetimestamp"] = page["basetimestamp"]
        result = self._authed(params)["edit"]
        if result.get("result") != "Success":
            raise WikiError("editfailed", json.dumps(result))
        return result.get("newrevid")


class Worker(threading.Thread):
    def __init__(self, cfg: Config, db: Database, wake: threading.Event, stop: threading.Event):
        super().__init__(name="sal-worker", daemon=True)
        self.cfg = cfg
        self.db = db
        self.wake = wake
        self.stop = stop
        self.wiki = Wiki(cfg)

    def run(self):
        while not self.stop.is_set():
            try:
                if self.cfg.wiki_enabled:
                    self.process_wiki()
                if self.cfg.phorge_enabled:
                    self.process_phorge()
            except Exception:
                log.exception("worker cycle failed")
            self.wake.wait(self.cfg.poll_interval)
            self.wake.clear()

    def pending(self, sink: str, limit: int) -> list[dict]:
        return self.db.run(
            f"SELECT * FROM sal_entries WHERE {sink}_state = 'pending' AND {sink}_next_at <= %s ORDER BY id LIMIT %s",
            (utcnow(), limit),
            fetch="all",
        )

    def defer(self, sink: str, rows: list[dict], error: str, permanent: bool = False):
        for row in rows:
            attempts = row[f"{sink}_attempts"] + 1
            state = "failed" if permanent or attempts >= self.cfg.max_attempts else "pending"
            self.db.run(
                f"UPDATE sal_entries SET {sink}_state = %s, {sink}_attempts = %s, {sink}_next_at = %s, "
                f"{sink}_error = %s WHERE id = %s AND {sink}_state = 'pending'",
                (state, attempts, utcnow() + backoff(attempts), error[:2000], row["id"]),
            )
        log.warning(
            "%s delivery of %s %s: %s", sink, [r["id"] for r in rows], "failed" if permanent else "deferred", error
        )

    def process_wiki(self):
        rows = self.pending("wiki", 50)
        if rows:
            self.wiki_batch(rows)

    def wiki_batch(self, rows: list[dict]):
        for attempt in range(3):
            try:
                page = self.wiki.fetch()
                text = page["text"]
                lines = {}
                for row in rows:
                    text, lines[row["id"]] = apply_wiki_op(text, row, self.cfg.phorge_base)
                revid = None
                if text != page["text"]:
                    revid = self.wiki.save(page, text, edit_summary(rows))
                for row in rows:
                    self.db.run(
                        "UPDATE sal_entries SET wiki_state = 'done', wiki_line = %s, wiki_revid = %s, "
                        "wiki_error = NULL WHERE id = %s AND wiki_state = 'pending' AND wiki_op = %s "
                        "AND updated_at <=> %s",
                        (lines[row["id"]], revid, row["id"], row["wiki_op"], row["updated_at"]),
                    )
                log.info("wiki: applied %s in revision %s", [r["id"] for r in rows], revid)
                return
            except WikiError as exc:
                if exc.code in ("editconflict", "articleexists") and attempt < 2:
                    continue
                if exc.transient or exc.code == "loginfailed":
                    self.defer("wiki", rows, str(exc))
                    return
                if len(rows) > 1:
                    for row in rows:
                        self.wiki_batch([row])
                    return
                self.defer("wiki", rows, str(exc), permanent=True)
                return
            except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
                self.defer("wiki", rows, f"{type(exc).__name__}: {exc}")
                return

    def process_phorge(self):
        for row in self.pending("phorge", 20):
            if self.stop.is_set():
                return
            self.deliver_phorge(row)

    def deliver_phorge(self, row: dict):
        if row["deleted"]:
            self.db.run("UPDATE sal_entries SET phorge_state = 'skipped' WHERE id = %s", (row["id"],))
            return
        payload = phorge_payload(self.cfg, row)
        request = urllib.request.Request(
            self.cfg.phorge_hook,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.cfg.phorge_token}",
                "Content-Type": "application/json",
                "User-Agent": self.cfg.user_agent,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode(errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            self.defer("phorge", [row], f"HTTP {exc.code}: {detail}", permanent=exc.code in (400, 413, 422))
            return
        except (urllib.error.URLError, OSError) as exc:
            self.defer("phorge", [row], f"{type(exc).__name__}: {exc}")
            return
        try:
            result = json.loads(raw) if raw.strip() else {}
        except ValueError:
            result = {}
        refs = result.get("refs") if isinstance(result, dict) else None
        if not isinstance(refs, list):
            refs = extract_refs(row["message"])
        refs = ",".join(str(r) for r in refs)[:1024]
        self.db.run(
            "UPDATE sal_entries SET phorge_state = 'done', phorge_refs = %s, phorge_error = NULL WHERE id = %s",
            (refs, row["id"]),
        )
        log.info("phorge: delivered %s (refs: %s)", row["id"], refs or "none")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Api:
    def __init__(self, cfg: Config, db: Database, wake: threading.Event):
        self.cfg = cfg
        self.db = db
        self.wake = wake

    def sink_states(self) -> tuple[str, str]:
        return (
            "pending" if self.cfg.wiki_enabled else "disabled",
            "pending" if self.cfg.phorge_enabled else "disabled",
        )

    def health(self) -> dict:
        row = self.db.run(
            "SELECT SUM(wiki_state = 'pending') AS wiki_pending, SUM(wiki_state = 'failed') AS wiki_failed, "
            "SUM(phorge_state = 'pending') AS phorge_pending, SUM(phorge_state = 'failed') AS phorge_failed, "
            "MAX(id) AS last_id FROM sal_entries",
            fetch="one",
        )
        return {"ok": True, **{k: int(v or 0) for k, v in row.items()}}

    def create(self, minion: str, body: dict) -> dict:
        user = clean_user(body.get("user"))
        message = clean_message(body.get("message"), self.cfg.max_message)
        is_command = bool(body.get("command"))
        exit_code = body.get("exit_code")
        if exit_code is not None and not isinstance(exit_code, int):
            raise ValueError("exit_code must be an integer")
        wiki_state, phorge_state = self.sink_states()
        now = utcnow()
        entry_id = self.db.run(
            "INSERT INTO sal_entries (created_at, user, host, minion, message, is_command, exit_code, "
            "wiki_state, wiki_next_at, phorge_state, phorge_next_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                now,
                user,
                short_host(minion),
                minion,
                message,
                int(is_command),
                exit_code,
                wiki_state,
                now,
                phorge_state,
                now,
            ),
        )
        self.wake.set()
        log.info("entry %s: %s@%s: %s", entry_id, user, short_host(minion), message)
        return serialize(self.db.get(entry_id))

    def query(self, params: dict) -> dict:
        where = []
        args = []
        if not truthy(params.get("deleted", "0")):
            where.append("deleted = 0")
        if params.get("q"):
            where.append("message LIKE %s")
            args.append(f"%{like_escape(params['q'])}%")
        if params.get("user"):
            where.append("user = %s")
            args.append(params["user"])
        if params.get("host"):
            host = params["host"]
            if host.endswith("*"):
                where.append("(host LIKE %s OR minion LIKE %s)")
                args += [like_escape(host[:-1]) + "%"] * 2
            else:
                where.append("(host = %s OR minion = %s)")
                args += [host, host]
        for key, op in (("since", ">="), ("until", "<")):
            if params.get(key):
                try:
                    args.append(parse_when(params[key]))
                except ValueError:
                    raise ValueError(f"cannot parse {key}: {params[key]}")
                where.append(f"created_at {op} %s")
        for key, op in (("before", "<"), ("after", ">")):
            if params.get(key):
                where.append(f"id {op} %s")
                args.append(int(params[key]))
        limit = max(1, min(int(params.get("limit", 25)), 500))
        order = "ASC" if params.get("after") else "DESC"
        sql = "SELECT * FROM sal_entries"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY id {order} LIMIT %s"
        rows = self.db.run(sql, (*args, limit), fetch="all")
        return {"entries": [serialize(r) for r in rows]}

    def fetch(self, entry_id: int, with_history: bool = False) -> dict:
        row = self.db.get(entry_id)
        if not row:
            raise ApiError(404, f"no entry #{entry_id}")
        result = serialize(row)
        if with_history:
            history = self.db.run("SELECT * FROM sal_history WHERE entry_id = %s ORDER BY id", (entry_id,), fetch="all")
            result["history"] = [
                {
                    "at": iso(h["at"]),
                    "user": h["actor_user"],
                    "host": h["actor_host"],
                    "action": h["action"],
                    "old_message": h["old_message"],
                    "new_message": h["new_message"],
                }
                for h in history
            ]
        return result

    def record(self, entry_id: int, minion: str, user: str, action: str, old, new):
        self.db.run(
            "INSERT INTO sal_history (entry_id, at, actor_user, actor_host, action, old_message, new_message) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (entry_id, utcnow(), user, short_host(minion), action, old, new),
        )

    def edit(self, minion: str, entry_id: int, body: dict) -> dict:
        user = clean_user(body.get("user"))
        message = clean_message(body.get("message"), self.cfg.max_message)
        row = self.db.get(entry_id)
        if not row or row["deleted"]:
            raise ApiError(404, f"no entry #{entry_id}")
        wiki_state, _ = self.sink_states()
        op = "update" if row["wiki_line"] else "insert"
        now = utcnow()
        self.db.run(
            "UPDATE sal_entries SET message = %s, updated_at = %s, wiki_op = %s, wiki_state = %s, "
            "wiki_attempts = 0, wiki_next_at = %s, wiki_error = NULL WHERE id = %s",
            (message, now, op, wiki_state, now, entry_id),
        )
        self.record(entry_id, minion, user, "edit", row["message"], message)
        self.wake.set()
        return serialize(self.db.get(entry_id))

    def delete(self, minion: str, entry_id: int, body: dict) -> dict:
        user = clean_user(body.get("user"))
        row = self.db.get(entry_id)
        if not row or row["deleted"]:
            raise ApiError(404, f"no entry #{entry_id}")
        wiki_state, _ = self.sink_states()
        now = utcnow()
        self.db.run(
            "UPDATE sal_entries SET deleted = 1, updated_at = %s, wiki_op = 'delete', wiki_state = %s, "
            "wiki_attempts = 0, wiki_next_at = %s, wiki_error = NULL, "
            "phorge_state = IF(phorge_state = 'pending', 'skipped', phorge_state) WHERE id = %s",
            (now, wiki_state, now, entry_id),
        )
        self.record(entry_id, minion, user, "delete", row["message"], None)
        self.wake.set()
        return serialize(self.db.get(entry_id))

    def retry(self, minion: str, entry_id: int, body: dict) -> dict:
        user = clean_user(body.get("user"))
        row = self.db.get(entry_id)
        if not row:
            raise ApiError(404, f"no entry #{entry_id}")
        now = utcnow()
        wiki_state, phorge_state = self.sink_states()
        self.db.run(
            "UPDATE sal_entries SET "
            "wiki_state = IF(wiki_state IN ('failed', 'pending'), %s, wiki_state), wiki_attempts = 0, "
            "wiki_next_at = %s, "
            "phorge_state = IF(phorge_state IN ('failed', 'pending') AND deleted = 0, %s, phorge_state), "
            "phorge_attempts = 0, phorge_next_at = %s WHERE id = %s",
            (wiki_state, now, phorge_state, now, entry_id),
        )
        self.record(entry_id, minion, user, "retry", None, None)
        self.wake.set()
        return serialize(self.db.get(entry_id))


ENTRY_PATH = re.compile(r"^/v1/entries/(\d+)(/retry|/history)?$")


def make_handler(cfg: Config, api: Api):
    class Handler(BaseHTTPRequestHandler):
        server_version = "sal-server/1.0"

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

        def respond(self, status: int, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(413, "request body too large")
            if not length:
                return {}
            try:
                body = json.loads(self.rfile.read(length).decode())
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "body is not valid JSON")
            if not isinstance(body, dict):
                raise ApiError(400, "body must be a JSON object")
            return body

        def authenticate(self) -> str:
            minion = self.headers.get("X-SAL-Host", "")
            auth = self.headers.get("Authorization", "")
            token = auth[7:] if auth.startswith("Bearer ") else ""
            if not verify_host(cfg.secret, minion, token):
                raise ApiError(401, "invalid host credentials")
            return minion

        def dispatch(self, method: str):
            try:
                url = urllib.parse.urlsplit(self.path)
                if method == "GET" and url.path == "/healthz":
                    return self.respond(200, api.health())
                minion = self.authenticate()
                params = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
                if url.path == "/v1/entries":
                    if method == "GET":
                        return self.respond(200, api.query(params))
                    if method == "POST":
                        return self.respond(201, api.create(minion, self.read_json()))
                match = ENTRY_PATH.match(url.path)
                if match:
                    entry_id = int(match.group(1))
                    action = match.group(2)
                    if method == "GET" and action in (None, "/history"):
                        return self.respond(200, api.fetch(entry_id, with_history=action == "/history"))
                    if method == "PATCH" and action is None:
                        return self.respond(200, api.edit(minion, entry_id, self.read_json()))
                    if method == "DELETE" and action is None:
                        return self.respond(200, api.delete(minion, entry_id, self.read_json()))
                    if method == "POST" and action == "/retry":
                        return self.respond(200, api.retry(minion, entry_id, self.read_json()))
                raise ApiError(404, "not found")
            except ApiError as exc:
                self.respond(exc.status, {"ok": False, "error": str(exc)})
            except ValueError as exc:
                self.respond(400, {"ok": False, "error": str(exc)})
            except Exception as exc:
                log.exception("request failed: %s %s", method, self.path)
                self.respond(500, {"ok": False, "error": f"internal error: {type(exc).__name__}"})

        def do_GET(self):
            self.dispatch("GET")

        def do_POST(self):
            self.dispatch("POST")

        def do_PATCH(self):
            self.dispatch("PATCH")

        def do_DELETE(self):
            self.dispatch("DELETE")

    return Handler


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("SAL_LOG_LEVEL", "INFO").upper(),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    cfg = Config(os.environ)
    missing = [
        name for name, value in (("SAL_SECRET", cfg.secret), ("SAL_DB_PASSWORD", cfg.db["password"])) if not value
    ]
    if cfg.wiki_enabled and not (cfg.wiki_user and cfg.wiki_password):
        missing.append("SAL_WIKI_USER/SAL_WIKI_PASSWORD")
    if cfg.phorge_enabled and not cfg.phorge_token:
        missing.append("SAL_PHORGE_TOKEN")
    if missing:
        log.error("missing configuration: %s", ", ".join(missing))
        return 1
    db = Database(cfg)
    db.ensure_schema()
    wake = threading.Event()
    stop = threading.Event()
    worker = Worker(cfg, db, wake, stop)
    worker.start()
    server = ThreadingHTTPServer((cfg.listen_host, cfg.listen_port), make_handler(cfg, Api(cfg, db, wake)))
    server.daemon_threads = True

    def shutdown(signum, frame):
        stop.set()
        wake.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    log.info("listening on %s:%s", cfg.listen_host, cfg.listen_port)
    server.serve_forever()
    worker.join(timeout=30)
    return 0


if __name__ == "__main__":
    sys.exit(main())
