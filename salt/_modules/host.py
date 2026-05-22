"""
Host management utilities — Icinga2 integration.

CLI examples::

    salt '*' host.downtime 'hostname.ovvin.wonet' '2h' 'Deploying new code'
    salt '*' host.downtime 'hostname.ovvin.wonet' '30m' 'Quick restart'
    salt '*' host.downtime 'hostname.ovvin.wonet' '1d' 'Extended maintenance'

Duration accepts: plain seconds (integer or string), or a string with a unit
suffix — s (seconds), m (minutes), h (hours), d (days).  Examples:
  '3600', 3600, '60m', '2h', '1d'

Pillar keys read (all under monitoring:):
  icinga_api_host      — hostname / IP of the Icinga2 master (required)
  icinga_api_user      — API username (default: root)
  icinga_api_password  — API password (required)
  icinga_api_port      — API port (default: 5665)
"""

import logging
import time

from salt.exceptions import CommandExecutionError

log = logging.getLogger(__name__)

__pillar__ = {}
__salt__ = {}


def __virtual__():
    return "host"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_duration(duration):
    """Return *duration* as an integer number of seconds."""
    s = str(duration).strip()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if s and s[-1] in units:
        try:
            return int(s[:-1]) * units[s[-1]]
        except ValueError:
            pass
    try:
        return int(s)
    except ValueError:
        raise CommandExecutionError(
            "Invalid duration {!r} — use seconds or a suffix: s/m/h/d".format(duration)
        )


def _api_cfg():
    mon = __pillar__.get("monitoring", {})
    host = mon.get("icinga_api_host")
    if not host:
        raise CommandExecutionError(
            "monitoring:icinga_api_host is not set in pillar"
        )
    user = mon.get("icinga_api_user", "root")
    password = mon.get("icinga_api_password")
    if not password:
        raise CommandExecutionError(
            "monitoring:icinga_api_password is not set in pillar"
        )
    port = int(mon.get("icinga_api_port", 5665))
    return host, port, user, password


def _api_post(path, payload):
    """POST *payload* (dict) to the Icinga2 API and return the parsed response."""
    import json
    import ssl
    import urllib.error
    import urllib.request

    host, port, user, password = _api_cfg()
    url = "https://{}:{}/v1/{}".format(host, port, path.lstrip("/"))

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-HTTP-Method-Override": "POST",
        },
    )

    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(None, url, user, password)
    auth_handler = urllib.request.HTTPBasicAuthHandler(password_mgr)

    # Icinga2 uses a self-signed cert by default; skip verification.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    https_handler = urllib.request.HTTPSHandler(context=ctx)

    opener = urllib.request.build_opener(auth_handler, https_handler)
    try:
        with opener.open(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise CommandExecutionError(
            "Icinga2 API returned HTTP {}: {}".format(exc.code, body)
        )
    except Exception as exc:
        raise CommandExecutionError("Icinga2 API request failed: {}".format(exc))


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def downtime(hostname, duration, reason):
    """
    Schedule a fixed downtime in Icinga2 for *hostname* and all its services,
    suppressing alerts for the given *duration*.

    :param hostname: Icinga2 host object name to downtime.
    :param duration: Length of the downtime.  Accepts an integer (seconds) or a
        string with a unit suffix: ``s``, ``m``, ``h``, ``d``.
    :param reason: Free-text comment recorded against the downtime.
    :returns: A summary string confirming the downtime was scheduled.

    CLI Example::

        salt '*' host.downtime 'hostname.ovvin.wonet' '2h' 'Deploying new code'
    """
    secs = _parse_duration(duration)
    now = int(time.time())
    end = now + secs

    _, _, api_user, _ = _api_cfg()

    payload = {
        "type": "Host",
        "filter": 'host.name == "{}"'.format(hostname),
        "start_time": now,
        "end_time": end,
        "duration": secs,
        "fixed": True,
        "comment": reason,
        "author": api_user,
        "all_services": 1,
    }

    result = _api_post("actions/schedule-downtime", payload)

    results = result.get("results", [])
    if not results:
        raise CommandExecutionError(
            "Icinga2 returned an empty response — host '{}' may not exist".format(
                hostname
            )
        )

    codes = {r.get("code") for r in results}
    if codes - {200}:
        errors = [r.get("status", "") for r in results if r.get("code") != 200]
        raise CommandExecutionError(
            "Icinga2 downtime failed: {}".format("; ".join(errors))
        )

    n = len(results)
    return "Downtime scheduled for '{}' + {} service(s) — {} for '{}'".format(
        hostname, n - 1, duration, reason
    )