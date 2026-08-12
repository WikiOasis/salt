#!/usr/bin/env python3
"""Sync an incident.io status page Atom feed into a Discord webhook.

One Discord message per incident, edited in place as the incident progresses.
Message IDs and the accumulated update history are kept in a JSON state file.

The Atom feed only exposes the *latest* update for each incident, so the update
timeline is built up across polls: every time an incident's update text changes,
a new line is appended to the stored history.

Environment:
  DISCORD_WEBHOOK_URL  (required)  Discord webhook to post/edit messages with.
  FEED_URL             (optional)  Defaults to the WikiOasis status feed.
  STATE_FILE           (optional)  Defaults to ./state.json
  STATUS_PAGE_URL      (optional)  Shown in the message footer.
  PRUNE_AFTER_DAYS     (optional)  Forget resolved incidents after N days (30).
  POLL_INTERVAL        (optional)  Seconds between polls. Unset/0 runs a single
                                   pass and exits, for use with a systemd timer.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import signal
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

ATOM = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "incidentio-sync/1.0 (+https://github.com/)"

# Components V2 opt-in. Required for the `components` payload below, and
# mutually exclusive with `content`/`embeds`. A plain (non-application-owned)
# incoming webhook like ours also silently drops the whole `components` field
# unless the request additionally carries `with_components=true` in the query
# string (see post_message/edit_message below) — without it Discord ends up
# with no displayable content at all and rejects the request as 50006
# "Cannot send an empty message", even though the flag and payload are fine.
IS_COMPONENTS_V2 = 1 << 15

# Component type IDs.
CONTAINER = 17
TEXT_DISPLAY = 10
SEPARATOR = 14

# Discord counts every character across all components against one budget.
TOTAL_CHAR_BUDGET = 3800

STATUS_COLORS = {
    "investigating": 0xED4245,  # red
    "identified": 0xE67E22,  # orange
    "monitoring": 0x5865F2,  # blurple
    "resolved": 0x57F287,  # green
    "scheduled": 0x5865F2,
    "in progress": 0xE67E22,
    "completed": 0x57F287,
}

log = logging.getLogger("incidentio-sync")


# --------------------------------------------------------------------------- #
# Feed parsing
# --------------------------------------------------------------------------- #


class _TextExtractor(HTMLParser):
    """Flatten incident.io's update HTML into plain text.

    <br> and block tags become newlines, <li> becomes a bullet; everything else
    is dropped. Discord renders markdown, not HTML, so tags have to go.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("br", "p", "div", "ul", "ol"):
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("p", "div", "ul", "ol", "li"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        joined = "".join(self.parts)
        joined = re.sub(r"[ \t]+", " ", joined)
        joined = re.sub(r" *\n *", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()


# incident.io flattens rich-text links into `text "label": https://url`.
# Collapse that back into a markdown link so Discord renders it cleanly.
_LINK_MARKUP = re.compile(r'(\S+) "[^"]*":\s*(https?://\S+)')


def html_to_text(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw or "")
    parser.close()
    return _LINK_MARKUP.sub(r"[\1](\2)", parser.text())


def parse_updated(value: str) -> datetime:
    """Parse an RFC 3339 timestamp, tolerating a trailing Z."""
    cleaned = (value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_entry(entry: ET.Element) -> dict | None:
    """Turn one Atom <entry> into an incident dict."""
    incident_id = (entry.findtext(f"{ATOM}id") or "").strip()
    if not incident_id:
        return None

    title = html.unescape((entry.findtext(f"{ATOM}title") or "Incident").strip())

    link_el = entry.find(f"{ATOM}link")
    link = (link_el.get("href") if link_el is not None else "") or incident_id
    link = re.sub(r"(?<!:)//incidents/", "/incidents/", link)

    body_html = entry.findtext(f"{ATOM}content") or entry.findtext(f"{ATOM}summary") or ""
    text = html_to_text(body_html)

    status = "Unknown"
    status_match = re.search(r"^\s*Status:\s*(.+)$", text, re.MULTILINE)
    if status_match:
        status = status_match.group(1).strip()

    # Components are listed as "Name (State)" bullets under an
    # "Affected components" heading at the end of the update body.
    components: list[str] = []
    split = re.split(r"\n?Affected components\n?", text, maxsplit=1)
    message = split[0]
    if len(split) > 1:
        for line in split[1].splitlines():
            line = line.strip().lstrip("-").strip()
            if line:
                components.append(line)
    # The feed's component order is not stable between polls; sort so an
    # unchanged incident doesn't look like it changed.
    components.sort()

    if status_match:
        message = message.replace(status_match.group(0), "", 1)
    message = message.strip()

    return {
        "id": incident_id,
        "title": title,
        "link": link,
        "status": status,
        "message": message,
        "components": components,
        "updated": parse_updated(entry.findtext(f"{ATOM}updated") or ""),
    }


class NotModified(Exception):
    """The feed is unchanged since our last poll."""


def fetch_feed(url: str, cache: dict | None = None) -> list[dict]:
    """Fetch and parse the feed.

    `cache` carries the ETag / Last-Modified from the previous poll so the
    server can answer 304 instead of re-sending the body; it is updated in
    place. Raises NotModified on a 304.
    """
    headers = {"User-Agent": USER_AGENT}
    if cache:
        if cache.get("etag"):
            headers["If-None-Match"] = cache["etag"]
        if cache.get("last_modified"):
            headers["If-Modified-Since"] = cache["last_modified"]

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            if cache is not None:
                cache["etag"] = response.headers.get("ETag") or ""
                cache["last_modified"] = response.headers.get("Last-Modified") or ""
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            raise NotModified from exc
        raise

    root = ET.fromstring(raw)

    incidents = []
    for entry in root.findall(f"{ATOM}entry"):
        parsed = parse_entry(entry)
        if parsed:
            incidents.append(parsed)
    # Oldest first, so the first-seen ordering of new incidents is stable.
    incidents.sort(key=lambda i: i["updated"])
    return incidents


# --------------------------------------------------------------------------- #
# Message building
# --------------------------------------------------------------------------- #


def text_display(content: str) -> dict:
    return {"type": TEXT_DISPLAY, "content": content}


def separator(spacing: int = 1) -> dict:
    return {"type": SEPARATOR, "divider": True, "spacing": spacing}


def accent_for(status: str) -> int | None:
    return STATUS_COLORS.get((status or "").strip().lower())


def format_updates(updates: list[dict], budget: int) -> str:
    """Render the update timeline newest-last, dropping oldest lines to fit."""
    lines = [
        f"[<t:{u['ts']}:R>] • **{u['status']}** • {u['message']}".strip()
        for u in updates
    ]

    while lines:
        rendered = "\n".join(lines)
        if len(rendered) <= budget:
            return rendered
        lines.pop(0)
        if lines:
            lines[0] = "-# _older updates truncated_\n" + lines[0]

    return "_No update details available._"


def build_payload(incident: dict, state: dict, status_page_url: str) -> dict:
    title = incident["title"]
    link = incident["link"]

    header = f"## [{title}]({link})"

    if incident["components"]:
        component_lines = "\n".join(f"- {c}" for c in incident["components"])
        components_block = f"**Affected components:**\n{component_lines}"
    else:
        components_block = "**Affected components:** _none reported_"

    footer = f"-# See {status_page_url} for more details."

    fixed = len(header) + len(components_block) + len(footer)
    updates_block = format_updates(state["updates"], max(TOTAL_CHAR_BUDGET - fixed, 200))

    container = {
        "type": CONTAINER,
        "accent_color": accent_for(incident["status"]),
        "spoiler": False,
        "components": [
            text_display(header),
            separator(2),
            text_display(components_block),
            separator(1),
            text_display(updates_block),
            separator(1),
            text_display(footer),
        ],
    }

    return {"flags": IS_COMPONENTS_V2, "components": [container]}


# --------------------------------------------------------------------------- #
# Discord
# --------------------------------------------------------------------------- #


def discord_request(url: str, payload: dict | None, method: str) -> dict | None:
    """Call the Discord API, retrying on rate limits and 5xx."""
    data = json.dumps(payload).encode() if payload is not None else None

    for attempt in range(5):
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
            return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if exc.code == 429:
                try:
                    retry_after = float(json.loads(body).get("retry_after", 5))
                except (ValueError, AttributeError):
                    retry_after = 5.0
                log.warning("Rate limited, sleeping %.1fs", retry_after)
                time.sleep(min(retry_after, 60))
                continue
            if exc.code == 404:
                raise MessageGone(body) from exc
            if 500 <= exc.code < 600 and attempt < 4:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"Discord {method} {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            if attempt < 4:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"Discord {method} failed: {exc}") from exc

    raise RuntimeError("Discord request exhausted retries")


class MessageGone(Exception):
    """The tracked message no longer exists and must be recreated."""


def post_message(webhook: str, payload: dict) -> str:
    result = discord_request(f"{webhook}?wait=true&with_components=true", payload, "POST")
    return str(result["id"])


def edit_message(webhook: str, message_id: str, payload: dict) -> None:
    discord_request(f"{webhook}/messages/{message_id}?with_components=true", payload, "PATCH")


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"incidents": {}}
    try:
        loaded = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        log.error("State file %s unreadable (%s); starting fresh", path, exc)
        return {"incidents": {}}
    loaded.setdefault("incidents", {})
    return loaded


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)  # atomic, so a crash mid-write can't corrupt state


def prune(state: dict, days: int) -> None:
    """Drop resolved incidents we stopped needing to track."""
    if days <= 0:
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    for incident_id, entry in list(state["incidents"].items()):
        if entry.get("status", "").lower() not in ("resolved", "completed"):
            continue
        if entry.get("last_seen", 0) < cutoff:
            del state["incidents"][incident_id]
            log.info("Pruned %s", incident_id)


# --------------------------------------------------------------------------- #
# Sync
# --------------------------------------------------------------------------- #


def sync_incident(incident: dict, state: dict, webhook: str, status_page_url: str) -> bool:
    """Create or update the Discord message for one incident.

    Returns True if anything changed.
    """
    incident_id = incident["id"]
    entry = state["incidents"].get(incident_id)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    update_ts = int(incident["updated"].timestamp())

    if entry is None:
        entry = {"message_id": None, "updates": [], "status": "", "last_seen": now_ts}
        state["incidents"][incident_id] = entry

    entry["last_seen"] = now_ts

    # The feed replaces the incident's body on each update, so a changed message
    # (or status) is how we detect that a new update was published.
    latest = entry["updates"][-1] if entry["updates"] else None
    is_new_update = (
        latest is None
        or latest["message"] != incident["message"]
        or latest["status"] != incident["status"]
    )

    if is_new_update:
        entry["updates"].append(
            {"ts": update_ts, "status": incident["status"], "message": incident["message"]}
        )

    changed = is_new_update or entry.get("components") != incident["components"]
    entry["status"] = incident["status"]
    entry["title"] = incident["title"]
    entry["components"] = incident["components"]

    if entry["message_id"] and not changed:
        return False

    payload = build_payload(incident, entry, status_page_url)

    if entry["message_id"]:
        try:
            edit_message(webhook, entry["message_id"], payload)
            log.info("Updated %s (%s)", incident["title"], incident["status"])
            return True
        except MessageGone:
            log.warning("Message for %s was deleted; reposting", incident["title"])
            entry["message_id"] = None

    entry["message_id"] = post_message(webhook, payload)
    log.info("Posted %s (%s)", incident["title"], incident["status"])
    return True


def poll_once(config: dict) -> int:
    """Run a single sync pass. Returns the number of failures."""
    state = load_state(config["state_path"])
    cache = state.setdefault("feed_cache", {})

    try:
        incidents = fetch_feed(config["feed_url"], cache)
    except NotModified:
        log.debug("Feed unchanged (304)")
        return 0
    except (urllib.error.URLError, ET.ParseError, OSError) as exc:
        log.error("Could not fetch %s: %s", config["feed_url"], exc)
        return 1

    log.debug("Fetched %d incidents", len(incidents))

    failures = 0
    for incident in incidents:
        try:
            if sync_incident(incident, state, config["webhook"], config["status_page_url"]):
                save_state(config["state_path"], state)  # persist per incident, so a
                # later failure can't cause a duplicate repost of an earlier one
        except Exception as exc:  # keep going; one bad incident shouldn't block others
            failures += 1
            log.error("Failed to sync %s: %s", incident.get("title"), exc)

    prune(state, config["prune_days"])
    save_state(config["state_path"], state)
    return failures


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(levelname)s %(message)s",
    )

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip().rstrip("/")
    if not webhook:
        log.error("DISCORD_WEBHOOK_URL is not set")
        return 2

    config = {
        "webhook": webhook,
        "feed_url": os.environ.get("FEED_URL", "https://status.wikioasis.org/feed.atom"),
        "state_path": Path(os.environ.get("STATE_FILE", "state.json")).expanduser(),
        "status_page_url": os.environ.get("STATUS_PAGE_URL", "status.wikioasis.org"),
        "prune_days": int(os.environ.get("PRUNE_AFTER_DAYS", "30")),
    }

    # POLL_INTERVAL turns this into a long-running daemon that polls on its own
    # schedule. Left unset, it runs one pass and exits (systemd timer style).
    interval = float(os.environ.get("POLL_INTERVAL", "0"))
    if interval <= 0:
        return 1 if poll_once(config) else 0

    running = {"stop": False}

    def handle_signal(signum, _frame):
        log.info("Received signal %s, shutting down", signum)
        running["stop"] = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    log.info("Polling %s every %.0fs", config["feed_url"], interval)
    while not running["stop"]:
        try:
            poll_once(config)
        except Exception as exc:  # never let the daemon die on a transient error
            log.exception("Poll failed: %s", exc)
        # Sleep in short slices so SIGTERM is handled promptly.
        deadline = time.monotonic() + interval
        while not running["stop"] and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))

    return 0


if __name__ == "__main__":
    sys.exit(main())
