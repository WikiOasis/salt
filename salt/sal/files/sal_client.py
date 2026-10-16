#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pwd
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CONFIG_PATH = os.environ.get("SAL_CONFIG", "/etc/sal/client.json")
LOG_USAGE = """usage: log <message...>
       <command> | log

Records <message> in the server admin log as user@host. Everything after
`log` is the message, verbatim. Use log-cli to search, show, edit or delete
entries, or to run and log a command."""


class ClientError(Exception):
    pass


def load_config() -> dict:
    try:
        with open(CONFIG_PATH) as handle:
            config = json.load(handle)
    except PermissionError:
        raise ClientError(f"cannot read {CONFIG_PATH}: you need to be in the 'sal' group, or use sudo")
    except FileNotFoundError:
        raise ClientError(f"{CONFIG_PATH} is missing; is the sal.client state applied on this host?")
    except ValueError:
        raise ClientError(f"{CONFIG_PATH} is not valid JSON")
    if os.environ.get("SAL_URL"):
        config["server_url"] = os.environ["SAL_URL"]
    for key in ("server_url", "host", "token"):
        if not config.get(key):
            raise ClientError(f"{CONFIG_PATH} has no {key}; check the sal pillar for this host")
    return config


def login_user() -> str:
    for candidate in (os.environ.get("SAL_USER"), os.environ.get("SUDO_USER")):
        if candidate and candidate != "root":
            return candidate
    try:
        with open("/proc/self/loginuid") as handle:
            uid = int(handle.read().strip())
        if uid not in (0, 4294967295):
            return pwd.getpwuid(uid).pw_name
    except (OSError, ValueError, KeyError):
        pass
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return str(os.getuid())


def request(config: dict, method: str, path: str, body: dict | None = None, params: dict | None = None):
    url = config["server_url"].rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "", False)})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {config['token']}",
            "X-SAL-Host": config["host"],
            "Content-Type": "application/json",
            "User-Agent": "sal-client/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("error", "")
        except ValueError:
            detail = ""
        raise ClientError(f"server returned {exc.code}" + (f": {detail}" if detail else ""))
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ClientError(f"cannot reach {config['server_url']}: {reason}")


def utc_time(value: str | None) -> str:
    if not value:
        return ""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")


def describe(entry: dict) -> str:
    if entry["command"]:
        text = f"$ {entry['message']}"
        if entry["exit_code"] not in (None, 0):
            text += f" (exit {entry['exit_code']})"
        return text
    return entry["message"]


def format_entry(entry: dict, verbose: bool = False) -> str:
    line = f"{utc_time(entry['created_at'])}  #{entry['id']:<6} {entry['user']}@{entry['host']}: {describe(entry)}"
    if entry.get("deleted"):
        line += "  [deleted]"
    if verbose:
        wiki = entry["wiki"]["state"]
        phorge = entry["phorge"]["state"]
        refs = " ".join(entry["phorge"]["refs"])
        line += f"  [wiki:{wiki} phorge:{phorge}{(' ' + refs) if refs else ''}]"
    return line


def post(config: dict, message: str, command: bool = False, exit_code: int | None = None) -> dict:
    body = {"user": login_user(), "message": message}
    if command:
        body["command"] = True
        body["exit_code"] = exit_code
    return request(config, "POST", "/v1/entries", body)


def main_log(argv: list[str]) -> int:
    if argv in (["-h"], ["--help"]):
        print(LOG_USAGE)
        return 0
    if argv and argv[0] == "--":
        argv = argv[1:]
    message = " ".join(argv)
    if not message.strip() and not sys.stdin.isatty():
        message = sys.stdin.read()
    if not message.strip():
        print(LOG_USAGE, file=sys.stderr)
        return 2
    try:
        entry = post(load_config(), message)
    except ClientError as exc:
        print(f"log: {exc}", file=sys.stderr)
        print(f"log: not logged: {' '.join(message.split())}", file=sys.stderr)
        return 1
    print(f"Logged #{entry['id']}: {entry['user']}@{entry['host']}: {entry['message']}")
    return 0


def add_filters(parser: argparse.ArgumentParser):
    parser.add_argument("-n", "--limit", type=int, default=25, help="number of entries (default 25, max 500)")
    parser.add_argument("-u", "--user", help="only entries by this user")
    parser.add_argument("-H", "--host", help="only entries from this host; a trailing * matches a prefix")
    parser.add_argument("--since", help="ISO date/time or relative age like 30m, 6h, 2d, 1w")
    parser.add_argument("--until", help="ISO date/time or relative age")
    parser.add_argument("--deleted", action="store_true", help="include deleted entries")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="show wiki/phorge delivery state")


def filter_params(args, **extra) -> dict:
    return {
        "limit": args.limit,
        "user": args.user,
        "host": args.host,
        "since": args.since,
        "until": args.until,
        "deleted": "1" if args.deleted else None,
        **extra,
    }


def print_entries(entries: list[dict], args):
    if args.json:
        print(json.dumps(entries, indent=2))
        return
    if not entries:
        print("no matching entries", file=sys.stderr)
    for entry in reversed(entries):
        print(format_entry(entry, args.verbose))


def cmd_list(config, args) -> int:
    entries = request(config, "GET", "/v1/entries", params=filter_params(args))["entries"]
    print_entries(entries, args)
    if not args.follow:
        return 0
    last = max((e["id"] for e in entries), default=0)
    try:
        while True:
            time.sleep(args.interval)
            fresh = request(config, "GET", "/v1/entries", params=filter_params(args, after=last))["entries"]
            for entry in fresh:
                print(json.dumps(entry) if args.json else format_entry(entry, args.verbose), flush=True)
                last = max(last, entry["id"])
    except KeyboardInterrupt:
        return 0


def cmd_search(config, args) -> int:
    entries = request(config, "GET", "/v1/entries", params=filter_params(args, q=" ".join(args.text)))["entries"]
    print_entries(entries, args)
    return 0


def cmd_show(config, args) -> int:
    entry = request(config, "GET", f"/v1/entries/{args.id}/history")
    if args.json:
        print(json.dumps(entry, indent=2))
        return 0
    print(format_entry(entry, verbose=True))
    print(f"  minion:  {entry['minion']}")
    if entry["updated_at"]:
        print(f"  updated: {utc_time(entry['updated_at'])}")
    for sink in ("wiki", "phorge"):
        state = entry[sink]
        extra = f", revision {state['revid']}" if state.get("revid") else ""
        extra += f", {state['attempts']} attempt(s)" if state["attempts"] else ""
        print(f"  {sink}:{' ' * (7 - len(sink))}{state['state']}{extra}")
        if state["error"]:
            print(f"           last error: {state['error']}")
    for item in entry.get("history", []):
        line = f"  {utc_time(item['at'])} {item['action']} by {item['user']}@{item['host']}"
        if item["action"] == "edit":
            line += f": {item['old_message']!r} -> {item['new_message']!r}"
        print(line)
    return 0


def cmd_run(config, args) -> int:
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print("log-cli run: no command given", file=sys.stderr)
        return 2
    try:
        code = subprocess.call(command)
    except FileNotFoundError:
        code = 127
        print(f"log-cli run: {command[0]}: command not found", file=sys.stderr)
    try:
        entry = post(config, shlex.join(command), command=True, exit_code=code)
        print(f"Logged #{entry['id']}: {entry['user']}@{entry['host']}: {describe(entry)}", file=sys.stderr)
    except ClientError as exc:
        print(f"log-cli: command ran but was not logged: {exc}", file=sys.stderr)
    return code


def cmd_edit(config, args) -> int:
    entry = request(
        config, "PATCH", f"/v1/entries/{args.id}", {"user": login_user(), "message": " ".join(args.message)}
    )
    print(f"Edited #{entry['id']}: {entry['user']}@{entry['host']}: {describe(entry)}")
    return 0


def cmd_delete(config, args) -> int:
    entry = request(config, "GET", f"/v1/entries/{args.id}")
    if not args.yes:
        if not sys.stdin.isatty():
            print("log-cli delete: refusing without --yes when not on a terminal", file=sys.stderr)
            return 2
        print(format_entry(entry))
        if input("Delete this entry and remove it from the wiki? [y/N] ").strip().lower() not in ("y", "yes"):
            print("not deleted")
            return 1
    request(config, "DELETE", f"/v1/entries/{args.id}", {"user": login_user()})
    print(f"Deleted #{args.id}")
    return 0


def cmd_retry(config, args) -> int:
    entry = request(config, "POST", f"/v1/entries/{args.id}/retry", {"user": login_user()})
    print(f"Requeued #{entry['id']}: wiki {entry['wiki']['state']}, phorge {entry['phorge']['state']}")
    return 0


def cmd_status(config, args) -> int:
    health = request(config, "GET", "/healthz")
    if args.json:
        print(json.dumps(health, indent=2))
        return 0
    print(f"server:  {config['server_url']} (last entry #{health.get('last_id', 0)})")
    print(f"wiki:    {health.get('wiki_pending', 0)} pending, {health.get('wiki_failed', 0)} failed")
    print(f"phorge:  {health.get('phorge_pending', 0)} pending, {health.get('phorge_failed', 0)} failed")
    print(f"you:     {login_user()}@{config['host'].split('.', 1)[0]}")
    return 0


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="log-cli",
        description="Query and manage the server admin log. To add an entry, use: log <message>",
    )
    sub = parser.add_subparsers(dest="cmd", metavar="<command>")

    p = sub.add_parser("list", help="show recent entries")
    add_filters(p)
    p.add_argument("-f", "--follow", action="store_true", help="keep printing new entries")
    p.add_argument("--interval", type=float, default=5, help="seconds between polls with --follow")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search", help="search entry text")
    p.add_argument("text", nargs="+")
    add_filters(p)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("show", help="show one entry with its delivery state and history")
    p.add_argument("id", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("run", help="run a command, then log it with its exit code")
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("edit", help="change an entry's text (also updates the wiki)")
    p.add_argument("id", type=int)
    p.add_argument("message", nargs="+")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("delete", help="delete an entry (also removes it from the wiki)")
    p.add_argument("id", type=int)
    p.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("retry", help="requeue failed wiki/phorge delivery for an entry")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_retry)

    p = sub.add_parser("status", help="show server health and delivery backlog")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)
    return parser


def main_cli(argv: list[str]) -> int:
    parser = build_cli()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 2
    try:
        return args.func(load_config(), args)
    except ClientError as exc:
        print(f"log-cli: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    name = os.path.basename(sys.argv[0])
    if name == "log-cli":
        return main_cli(sys.argv[1:])
    return main_log(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
