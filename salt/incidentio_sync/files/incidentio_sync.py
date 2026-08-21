#!/usr/bin/env python3
"""Sync an incident.io status page into a Discord webhook.

Two kinds of message are maintained in the channel:

  * One message per incident/maintenance, edited in place as it progresses.
  * A single "sticky" overview message listing every component and its current
    status, kept at the bottom of the channel.

Message IDs live in a JSON state file so restarts don't repost anything.

Data source
-----------
The status page itself (not the Atom feed) is polled. incident.io renders the
page with Next.js and embeds the entire page model — component roster, group
structure, ongoing incidents and their *full* update timelines — in the RSC
payload as `self.__next_f.push([1, "..."])` script chunks. Scraping that gives
us everything the page shows, which the public feed and API do not:

  * The Atom feed exposes only the latest update per incident, so the old
    implementation had to accumulate a timeline across polls and could miss
    updates published between two polls. The page carries the real timeline.
  * Neither the feed nor /api/v1/summary lists components that are *healthy*,
    and neither exposes group structure — both are required to render an
    overview of *all* components.

This is an undocumented internal payload, so it can change shape without
notice. Every parse is defensive and there are two fallbacks: the documented
/api/v1/summary endpoint (incidents only, no roster) and the component roster
cached in the state file from the last good parse. A broken scrape therefore
degrades the overview rather than taking incident sync down with it.

Environment:
  DISCORD_WEBHOOK_URL  (required)  Discord webhook to post/edit messages with.
  STATUS_PAGE_URL      (optional)  Status page origin. Defaults to the
                                   WikiOasis page. Also shown in footers.
  STATE_FILE           (optional)  Defaults to ./state.json
  OVERVIEW_ENABLED     (optional)  Set 0/false to skip the sticky overview.
  PRUNE_AFTER_DAYS     (optional)  Forget resolved incidents after N days (30).
  POLL_INTERVAL        (optional)  Seconds between polls. Unset/0 runs a single
                                   pass and exits, for use with a systemd timer.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER_AGENT = "incidentio-sync/2.0 (+https://github.com/WikiOasis/incidentio-sync)"

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

# incident.io incident/maintenance lifecycle statuses.
STATUS_COLORS = {
    "investigating": 0xED4245,  # red
    "identified": 0xE67E22,  # orange
    "monitoring": 0x5865F2,  # blurple
    "resolved": 0x57F287,  # green
    "scheduled": 0x5865F2,
    "in_progress": 0xE67E22,
    "completed": 0x57F287,
}

# incident.io component statuses, worst last. The ordering is what decides the
# overall page status and the accent colour of the overview.
COMPONENT_STATUS_ORDER = [
    "operational",
    "under_maintenance",
    "degraded_performance",
    "partial_outage",
    "full_outage",
]

COMPONENT_STATUS_EMOJI = {
    "operational": "🟢",
    "under_maintenance": "🔧",
    "degraded_performance": "🟡",
    "partial_outage": "🟠",
    "full_outage": "🔴",
    "unknown": "⚪",
}

COMPONENT_STATUS_COLORS = {
    "operational": 0x57F287,
    "under_maintenance": 0x5865F2,
    "degraded_performance": 0xFEE75C,
    "partial_outage": 0xE67E22,
    "full_outage": 0xED4245,
    "unknown": 0x99AAB5,
}

OVERALL_HEADLINE = {
    "operational": "All systems operational",
    "under_maintenance": "Maintenance in progress",
    "degraded_performance": "Degraded performance",
    "partial_outage": "Partial outage",
    "full_outage": "Major outage",
    "unknown": "Status unknown",
}

log = logging.getLogger("incidentio-sync")


def humanise(value: str) -> str:
    """`partial_outage` -> `Partial outage`."""
    return (value or "unknown").replace("_", " ").strip().capitalize()


def severity(status: str) -> int:
    try:
        return COMPONENT_STATUS_ORDER.index(status)
    except ValueError:
        return 0  # unknown statuses must not outrank a real outage


# --------------------------------------------------------------------------- #
# Status page scraping
# --------------------------------------------------------------------------- #


class ScrapeError(Exception):
    """The status page did not contain a payload we could parse."""


_RSC_CHUNK = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>", re.S)


def http_get(url: str, timeout: int = 30) -> bytes:
    """GET a URL, transparently gunzipping the response.

    The status page sends no ETag/Last-Modified, so conditional requests are
    not an option and every poll pulls the whole document. gzip roughly halves
    it, which matters at a 15s poll interval.
    """
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return raw


def rsc_payload(html: str) -> str:
    """Concatenate the Next.js flight chunks back into one string."""
    parts = []
    for chunk in _RSC_CHUNK.findall(html):
        try:
            decoded = json.loads(chunk)
        except ValueError:
            continue  # a chunk we can't read is not fatal; others may still parse
        if len(decoded) > 1 and isinstance(decoded[1], str):
            parts.append(decoded[1])
    return "".join(parts)


def extract_object(payload: str, key: str) -> dict:
    """Pull the JSON object that follows `"<key>":` out of the flight payload.

    The payload is not valid JSON as a whole (it is a stream of framed chunks),
    so the object is located by key and delimited by brace matching, skipping
    braces that appear inside string literals.
    """
    marker = f'"{key}":{{'
    start = payload.find(marker)
    if start < 0:
        raise ScrapeError(f"no {key!r} object in page payload")
    start = payload.index("{", start + len(marker) - 1)

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(payload)):
        char = payload[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(payload[start : index + 1])
                except ValueError as exc:
                    raise ScrapeError(f"{key!r} object is not valid JSON: {exc}") from exc
    raise ScrapeError(f"{key!r} object is truncated")


def clean(value):
    """Replace React's `$undefined` sentinel with None, recursively."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if value == "$undefined":
        return None
    return value


def scrape_object(url: str, key: str) -> dict:
    try:
        html = http_get(url).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        raise ScrapeError(f"could not fetch {url}: {exc}") from exc
    payload = rsc_payload(html)
    if not payload:
        raise ScrapeError(f"no Next.js payload in {url}")
    return clean(extract_object(payload, key))


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #


def update_text(update: dict) -> str:
    """Best available plain/markdown rendering of one incident update.

    incident.io stores the rich text three ways; `markdown` is already close
    enough to Discord's dialect to pass straight through.
    """
    message = update.get("message") or {}
    if isinstance(message, dict) and message.get("markdown"):
        return str(message["markdown"]).strip()
    return str(update.get("message_string") or "").strip()


def parse_ts(value: str | None) -> datetime:
    cleaned = (value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalise_incident(
    raw: dict, base_url: str, names: dict, default_kind: str = "incident"
) -> dict | None:
    """Turn a page-model incident/maintenance into our internal shape.

    Also accepts the flatter shape /api/v1/summary returns, which carries only
    the latest update (as `last_update_message`) instead of a timeline.
    """
    incident_id = (raw.get("id") or "").strip()
    if not incident_id:
        return None

    kind = raw.get("type") or default_kind
    path = "maintenances" if kind == "maintenance" else "incidents"

    updates = []
    for update in raw.get("updates") or []:
        updates.append(
            {
                "id": update.get("id") or "",
                "ts": int(parse_ts(update.get("published_at")).timestamp()),
                "status": update.get("to_status") or raw.get("status") or "unknown",
                "message": update_text(update),
            }
        )
    if not updates and raw.get("last_update_message"):
        updates.append(
            {
                "id": "",
                "ts": int(parse_ts(raw.get("last_update_at")).timestamp()),
                "status": raw.get("status") or "unknown",
                "message": str(raw["last_update_message"]).strip(),
            }
        )
    updates.sort(key=lambda u: u["ts"])

    # Component names are resolved against the roster; an id we have no name
    # for is skipped rather than shown as a meaningless ULID.
    components = []
    for affected in raw.get("affected_components") or []:
        # The page model keys this `component_id`; the summary API keys it `id`.
        name = names.get(affected.get("component_id") or affected.get("id"))
        if not name:
            continue
        status = affected.get("current_status") or affected.get("status") or "unknown"
        components.append(f"{name} ({humanise(status)})")
    components.sort()

    return {
        "id": incident_id,
        "kind": kind,
        "title": raw.get("name") or "Incident",
        "link": f"{base_url}/{path}/{incident_id}",
        "status": raw.get("status") or "unknown",
        "components": components,
        "updates": updates,
        "starts_at": raw.get("starts_at") or raw.get("published_at"),
        "ends_at": raw.get("ends_at"),
        "updated": updates[-1]["ts"] if updates else int(parse_ts(raw.get("published_at")).timestamp()),
    }


def roster_from_structure(structure: dict) -> list[dict]:
    """Flatten the page's display structure into an ordered component list.

    Ordering and grouping are taken from `structure` (what the page actually
    renders) rather than the flat `components` array, so the overview reads the
    same top-to-bottom as the status page. Hidden entries are omitted.
    """
    roster: list[dict] = []
    for item in structure.get("items") or []:
        component = item.get("component")
        if component and not component.get("hidden"):
            roster.append(
                {
                    "id": component.get("component_id"),
                    "name": (component.get("name") or "").strip(),
                    "group": None,
                }
            )
            continue
        group = item.get("group")
        if not group or group.get("hidden"):
            continue
        group_name = (group.get("name") or "").strip()
        for member in group.get("components") or []:
            if member.get("hidden"):
                continue
            roster.append(
                {
                    "id": member.get("component_id"),
                    "name": (member.get("name") or "").strip(),
                    "group": group_name,
                }
            )
    return [c for c in roster if c["id"] and c["name"]]


def build_model(summary: dict, base_url: str) -> dict:
    """Reduce a page summary into the roster, per-component status and incidents."""
    roster = roster_from_structure(summary.get("structure") or {})
    if not roster:
        # Structure missing (or shape changed): fall back to the flat list, which
        # loses grouping and ordering but still names every component.
        roster = [
            {"id": c.get("id"), "name": (c.get("name") or "").strip(), "group": None}
            for c in summary.get("components") or []
            if c.get("id") and c.get("name")
        ]

    names = {c["id"]: c["name"] for c in roster}

    # The page model puts in-progress and scheduled maintenance in one list and
    # tags each with `type`; the summary API splits them and tags nothing, so
    # the kind is defaulted per source list.
    incidents = []
    for key, kind in (
        ("ongoing_incidents", "incident"),
        ("in_progress_maintenances", "maintenance"),
        ("scheduled_maintenances", "maintenance"),
    ):
        for raw in summary.get(key) or []:
            parsed = normalise_incident(raw, base_url, names, kind)
            if parsed:
                incidents.append(parsed)

    # A component only appears in `affected_components` when something is wrong
    # with it, so everything on the roster starts operational and is downgraded
    # by whatever is currently impacting it. Worst impact wins.
    statuses = {c["id"]: "operational" for c in roster}
    affected = list(summary.get("affected_components") or [])
    for key in ("ongoing_incidents", "in_progress_maintenances"):
        for raw in summary.get(key) or []:
            affected.extend(raw.get("affected_components") or [])

    for entry in affected:
        component_id = entry.get("component_id") or entry.get("id")
        if component_id not in statuses:
            continue
        status = entry.get("current_status") or entry.get("status") or "operational"
        if severity(status) > severity(statuses[component_id]):
            statuses[component_id] = status

    incidents.sort(key=lambda i: i["updated"])
    return {"roster": roster, "statuses": statuses, "incidents": incidents}


def fetch_model(base_url: str, state: dict) -> dict:
    """Fetch and normalise the current page model, with fallbacks.

    Primary source is the rendered page. If its payload can't be parsed the
    documented summary API stands in — it carries incidents but no component
    roster, so the roster cached from the last good scrape is reused and the
    overview is flagged stale.
    """
    try:
        summary = scrape_object(base_url + "/", "summary")
        model = build_model(summary, base_url)
        if model["roster"]:
            state["roster_cache"] = model["roster"]
            model["stale_roster"] = False
            return model
        raise ScrapeError("page payload contained no components")
    except ScrapeError as exc:
        log.warning("Falling back to summary API: %s", exc)

    raw = http_get(f"{base_url}/api/v1/summary")
    summary = json.loads(raw)
    # The API omits `structure`/`components`; splice in the cached roster so
    # component names still resolve and the overview can still be rendered.
    cached = state.get("roster_cache") or []
    summary["structure"] = {
        "items": [
            {
                "component": {
                    "component_id": c["id"],
                    "name": c["name"],
                    "hidden": False,
                },
                "group": None,
            }
            if not c.get("group")
            else {
                "component": None,
                "group": {
                    "name": c["group"],
                    "hidden": False,
                    "components": [
                        {"component_id": c["id"], "name": c["name"], "hidden": False}
                    ],
                },
            }
            for c in cached
        ]
    }
    model = build_model(summary, base_url)
    model["stale_roster"] = True
    return model


def fetch_final_incident(base_url: str, incident_id: str, kind: str, names: dict) -> dict | None:
    """Re-read one incident's own page.

    Resolved incidents drop out of the page summary immediately, which would
    otherwise leave the channel showing an incident permanently stuck on its
    last in-flight update. The incident's own page still carries the closing
    update, so it is fetched once on disappearance.
    """
    path = "maintenances" if kind == "maintenance" else "incidents"
    try:
        raw = scrape_object(f"{base_url}/{path}/{incident_id}", "incident")
    except ScrapeError as exc:
        log.warning("Could not read final state of %s: %s", incident_id, exc)
        return None
    raw.setdefault("type", kind)
    return normalise_incident(raw, base_url, names)


# --------------------------------------------------------------------------- #
# Message building
# --------------------------------------------------------------------------- #


def text_display(content: str) -> dict:
    return {"type": TEXT_DISPLAY, "content": content}


def separator(spacing: int = 1) -> dict:
    return {"type": SEPARATOR, "divider": True, "spacing": spacing}


def format_updates(updates: list[dict], budget: int) -> str:
    """Render the update timeline newest-last, dropping oldest lines to fit."""
    lines = [
        f"[<t:{u['ts']}:R>] • **{humanise(u['status'])}** • {u['message']}".strip()
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


def build_incident_payload(incident: dict, status_page_url: str) -> dict:
    title = incident["title"]
    header = f"## [{title}]({incident['link']})"

    if incident["components"]:
        component_lines = "\n".join(f"- {c}" for c in incident["components"])
        components_block = f"**Affected components:**\n{component_lines}"
    else:
        components_block = "**Affected components:** _none reported_"

    footer = f"-# See {status_page_url} for more details."

    fixed = len(header) + len(components_block) + len(footer)
    updates_block = format_updates(incident["updates"], max(TOTAL_CHAR_BUDGET - fixed, 200))

    container = {
        "type": CONTAINER,
        "accent_color": STATUS_COLORS.get((incident["status"] or "").strip().lower()),
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


def build_overview_payload(model: dict, status_page_url: str, checked_at: int) -> dict:
    """Render the sticky all-components overview."""
    roster = model["roster"]
    statuses = model["statuses"]

    overall = "operational" if roster else "unknown"
    for component in roster:
        status = statuses.get(component["id"], "unknown")
        if severity(status) > severity(overall):
            overall = status

    emoji = COMPONENT_STATUS_EMOJI.get(overall, COMPONENT_STATUS_EMOJI["unknown"])
    header = f"## {emoji} {OVERALL_HEADLINE.get(overall, OVERALL_HEADLINE['unknown'])}"

    lines: list[str] = []
    current_group: str | None = None
    for component in roster:
        if component["group"] != current_group:
            current_group = component["group"]
            if current_group:
                lines.append(f"**{current_group}**")
        status = statuses.get(component["id"], "unknown")
        bullet = COMPONENT_STATUS_EMOJI.get(status, COMPONENT_STATUS_EMOJI["unknown"])
        indent = "> " if component["group"] else ""
        lines.append(f"{indent}{bullet} {component['name']} — {humanise(status)}")

    body = "\n".join(lines) if lines else "_No components published._"

    active = [i for i in model["incidents"] if i["status"] not in ("resolved", "completed")]
    if active:
        active_lines = "\n".join(f"- [{i['title']}]({i['link']}) — {humanise(i['status'])}" for i in active)
        active_block = f"**Active incidents & maintenance:**\n{active_lines}"
    else:
        active_block = "**Active incidents & maintenance:** _none_"

    footer = f"-# Updated <t:{checked_at}:R> • {status_page_url}"
    if model.get("stale_roster"):
        footer += "\n-# _Component list may be out of date — status page could not be read in full._"

    # Trim the component list rather than the header/footer if we somehow blow
    # the budget (a very large roster).
    budget = TOTAL_CHAR_BUDGET - len(header) - len(active_block) - len(footer)
    if len(body) > budget:
        body = body[: max(budget - 40, 0)].rstrip() + "\n-# _list truncated_"

    container = {
        "type": CONTAINER,
        "accent_color": COMPONENT_STATUS_COLORS.get(overall),
        "spoiler": False,
        "components": [
            text_display(header),
            separator(2),
            text_display(body),
            separator(1),
            text_display(active_block),
            separator(1),
            text_display(footer),
        ],
    }

    return {"flags": IS_COMPONENTS_V2, "components": [container]}


def overview_fingerprint(model: dict) -> str:
    """Hash everything the overview shows *except* the relative timestamp.

    The footer uses a Discord relative timestamp, which the client re-renders
    on its own, so an unchanged page needs no edit at all.
    """
    material = {
        "roster": [(c["group"], c["name"], model["statuses"].get(c["id"])) for c in model["roster"]],
        "active": sorted(
            (i["id"], i["status"], i["title"])
            for i in model["incidents"]
            if i["status"] not in ("resolved", "completed")
        ),
        "stale": bool(model.get("stale_roster")),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Discord
# --------------------------------------------------------------------------- #


class MessageGone(Exception):
    """The tracked message no longer exists and must be recreated."""


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


def post_message(webhook: str, payload: dict) -> str:
    result = discord_request(f"{webhook}?wait=true&with_components=true", payload, "POST")
    return str(result["id"])


def edit_message(webhook: str, message_id: str, payload: dict) -> None:
    discord_request(f"{webhook}/messages/{message_id}?with_components=true", payload, "PATCH")


def delete_message(webhook: str, message_id: str) -> None:
    try:
        discord_request(f"{webhook}/messages/{message_id}", None, "DELETE")
    except MessageGone:
        pass  # already gone is the outcome we wanted


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #


# Feed-era state keyed incidents by their Atom <id>, which is a URL of the form
# `https://status.wikioasis.org//incidents/<ULID>` (the doubled slash is
# incident.io's, not a typo). The page model keys by the bare ULID.
_LEGACY_KEY = re.compile(r"/(incidents|maintenances)/([0-9A-Za-z]+)/?$")


def migrate_state(state: dict) -> bool:
    """Re-key state written by the feed-based version. Returns True if changed.

    Without this every incident already tracked would look brand new and get
    reposted, orphaning the message we are already editing.
    """
    changed = False
    for key, entry in list(state["incidents"].items()):
        match = _LEGACY_KEY.search(key)
        if not match:
            continue
        del state["incidents"][key]
        changed = True
        incident_id = match.group(2)
        if incident_id in state["incidents"]:
            continue  # already re-keyed on an earlier run; keep the newer entry
        entry["kind"] = "maintenance" if match.group(1) == "maintenances" else "incident"
        # The old `updates` list was accumulated across polls and may not match
        # the authoritative timeline, so drop it and clear the fingerprint: the
        # next poll re-renders the existing message once from real data.
        entry.pop("updates", None)
        entry["fingerprint"] = None
        entry["update_count"] = 0
        state["incidents"][incident_id] = entry
        log.info("Migrated state key for %s", incident_id)
    return changed


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"incidents": {}}
    try:
        loaded = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        log.error("State file %s unreadable (%s); starting fresh", path, exc)
        return {"incidents": {}}
    loaded.setdefault("incidents", {})
    loaded.pop("feed_cache", None)  # ETag cache for a feed we no longer fetch
    if migrate_state(loaded):
        save_state(path, loaded)
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
        if entry.get("status", "") not in ("resolved", "completed"):
            continue
        if entry.get("last_seen", 0) < cutoff:
            del state["incidents"][incident_id]
            log.info("Pruned %s", incident_id)


# --------------------------------------------------------------------------- #
# Sync
# --------------------------------------------------------------------------- #


def incident_fingerprint(incident: dict) -> str:
    material = {
        "title": incident["title"],
        "status": incident["status"],
        "components": incident["components"],
        "updates": [(u["ts"], u["status"], u["message"]) for u in incident["updates"]],
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def sync_incident(incident: dict, state: dict, webhook: str, status_page_url: str) -> str | None:
    """Create or update the Discord message for one incident.

    Returns "posted", "edited", or None if nothing changed.
    """
    incident_id = incident["id"]
    entry = state["incidents"].setdefault(
        incident_id, {"message_id": None, "fingerprint": None, "kind": incident["kind"]}
    )
    entry["last_seen"] = int(datetime.now(timezone.utc).timestamp())
    entry["status"] = incident["status"]
    entry["title"] = incident["title"]
    entry["kind"] = incident["kind"]

    fingerprint = incident_fingerprint(incident)
    if entry["message_id"] and entry.get("fingerprint") == fingerprint:
        return None

    # A status page never retracts an update, so a timeline that got *shorter*
    # means we read a degraded source (the summary API fallback carries only the
    # latest update). Editing on that would replace a full timeline with a
    # single line; wait for a good read instead.
    if entry["message_id"] and len(incident["updates"]) < entry.get("update_count", 0):
        log.warning(
            "Skipping %s: source returned %d updates, previously had %d",
            incident["title"],
            len(incident["updates"]),
            entry.get("update_count", 0),
        )
        return None

    payload = build_incident_payload(incident, status_page_url)

    if entry["message_id"]:
        try:
            edit_message(webhook, entry["message_id"], payload)
            entry["fingerprint"] = fingerprint
            entry["update_count"] = len(incident["updates"])
            log.info("Updated %s (%s)", incident["title"], incident["status"])
            return "edited"
        except MessageGone:
            log.warning("Message for %s was deleted; reposting", incident["title"])
            entry["message_id"] = None

    entry["message_id"] = post_message(webhook, payload)
    entry["fingerprint"] = fingerprint
    entry["update_count"] = len(incident["updates"])
    log.info("Posted %s (%s)", incident["title"], incident["status"])
    return "posted"


def close_disappeared(model: dict, state: dict, config: dict) -> bool:
    """Catch incidents that vanished from the page because they resolved."""
    live = {i["id"] for i in model["incidents"]}
    names = {c["id"]: c["name"] for c in model["roster"]}
    posted = False

    for incident_id, entry in list(state["incidents"].items()):
        if incident_id in live or entry.get("closed"):
            continue
        if not entry.get("message_id"):
            entry["closed"] = True
            continue
        final = fetch_final_incident(
            config["base_url"], incident_id, entry.get("kind", "incident"), names
        )
        if final is None:
            continue  # try again next poll rather than leaving a stale message
        if sync_incident(final, state, config["webhook"], config["status_page_url"]):
            posted = True
        entry["closed"] = True

    return posted


def sync_overview(model: dict, state: dict, config: dict, move_to_bottom: bool) -> None:
    """Keep the all-components overview as the last message in the channel.

    A webhook can't pin, and can't see messages it didn't send, so "sticky"
    means "reposted whenever *we* add a message above it". Anything posted by
    another bot or a human will still land underneath it until our next post.
    """
    overview = state.setdefault("overview", {"message_id": None, "fingerprint": None})
    fingerprint = overview_fingerprint(model)
    checked_at = int(datetime.now(timezone.utc).timestamp())

    if overview["message_id"] and not move_to_bottom and overview.get("fingerprint") == fingerprint:
        return

    payload = build_overview_payload(model, config["status_page_url"], checked_at)

    if overview["message_id"] and move_to_bottom:
        delete_message(config["webhook"], overview["message_id"])
        overview["message_id"] = None
        save_state(config["state_path"], state)  # never leave an orphan id behind

    if overview["message_id"]:
        try:
            edit_message(config["webhook"], overview["message_id"], payload)
            overview["fingerprint"] = fingerprint
            log.info("Overview updated")
            return
        except MessageGone:
            log.warning("Overview message was deleted; reposting")
            overview["message_id"] = None

    overview["message_id"] = post_message(config["webhook"], payload)
    overview["fingerprint"] = fingerprint
    log.info("Overview posted")


def poll_once(config: dict) -> int:
    """Run a single sync pass. Returns the number of failures."""
    state = load_state(config["state_path"])

    try:
        model = fetch_model(config["base_url"], state)
    except (urllib.error.URLError, ScrapeError, ValueError, OSError) as exc:
        log.error("Could not read %s: %s", config["base_url"], exc)
        return 1

    log.debug(
        "%d components, %d live incidents", len(model["roster"]), len(model["incidents"])
    )

    failures = 0
    posted = False
    for incident in model["incidents"]:
        try:
            result = sync_incident(
                incident, state, config["webhook"], config["status_page_url"]
            )
            if result:
                posted = posted or result == "posted"
                save_state(config["state_path"], state)  # persist per incident, so a
                # later failure can't cause a duplicate repost of an earlier one
        except Exception as exc:  # keep going; one bad incident shouldn't block others
            failures += 1
            log.error("Failed to sync %s: %s", incident.get("title"), exc)

    try:
        posted = close_disappeared(model, state, config) or posted
    except Exception as exc:
        failures += 1
        log.error("Failed to close resolved incidents: %s", exc)
    save_state(config["state_path"], state)

    if config["overview_enabled"]:
        try:
            sync_overview(model, state, config, move_to_bottom=posted)
        except Exception as exc:
            failures += 1
            log.error("Failed to sync overview: %s", exc)

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

    page = os.environ.get("STATUS_PAGE_URL", "https://status.wikioasis.org").strip()
    if not page.startswith(("http://", "https://")):
        page = "https://" + page
    base_url = page.rstrip("/")

    config = {
        "webhook": webhook,
        "base_url": base_url,
        # Bare host reads better in the message footers than the full origin.
        "status_page_url": urllib.parse.urlparse(base_url).netloc or base_url,
        "state_path": Path(os.environ.get("STATE_FILE", "state.json")).expanduser(),
        "prune_days": int(os.environ.get("PRUNE_AFTER_DAYS", "30")),
        "overview_enabled": os.environ.get("OVERVIEW_ENABLED", "1").strip().lower()
        not in ("0", "false", "no", ""),
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

    log.info("Polling %s every %.0fs", base_url, interval)
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
