"""
HAProxy runtime management via the stats socket.

All commands communicate with the running HAProxy instance directly
over the stats socket — no config reload required.

The socket path is read from pillar (haproxy:stats_socket) with a
fallback of /run/haproxy/admin.sock.

CLI examples::

    salt 'proxy*' haproxy.status
    salt 'proxy*' haproxy.depool app_servers app01
    salt 'proxy*' haproxy.repool app_servers app01
    salt 'proxy*' haproxy.route_list
    salt 'proxy*' haproxy.route_set app.example.com app_servers
    salt 'proxy*' haproxy.route_del app.example.com
"""

import logging
import shlex

from salt.exceptions import CommandExecutionError

log = logging.getLogger(__name__)

# Injected by Salt's loader at import time
__pillar__ = {}
__salt__ = {}


def __virtual__():
    return "haproxy"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _socket():
    return __pillar__.get("haproxy", {}).get(
        "stats_socket", "/run/haproxy/admin.sock"
    )


def _send(command):
    """Send a single command to the HAProxy runtime socket and return stdout."""
    cmd = "printf '%s\\n' {} | socat stdio {}".format(
        shlex.quote(command), shlex.quote(_socket())
    )
    result = __salt__["cmd.run_all"](cmd, python_shell=True)
    if result["retcode"] != 0:
        raise CommandExecutionError(result.get("stderr") or result.get("stdout", ""))
    return result["stdout"].strip()


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def status():
    """
    Return the current state of all backend servers as a list of dicts.

    CLI Example::

        salt 'proxy*' haproxy.status
    """
    raw = _send("show stat")
    rows = []
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split(",")
        if len(fields) < 19 or fields[1] in ("FRONTEND", "BACKEND"):
            continue
        rows.append(
            {
                "backend": fields[0],
                "server": fields[1],
                "status": fields[17],
                "weight": fields[18],
            }
        )
    return rows


def depool(backend, server):
    """
    Disable a server in the specified backend via the runtime socket.
    Takes effect immediately — no reload required.

    CLI Example::

        salt 'proxy*' haproxy.depool app_servers app01
    """
    _send("disable server {}/{}".format(backend, server))
    return "{}/{} depooled".format(backend, server)


def repool(backend, server):
    """
    Re-enable a server in the specified backend via the runtime socket.

    CLI Example::

        salt 'proxy*' haproxy.repool app_servers app01
    """
    _send("enable server {}/{}".format(backend, server))
    return "{}/{} repooled".format(backend, server)


def route_list():
    """
    Return all active hostname → backend routes from the live map as a dict.

    CLI Example::

        salt 'proxy*' haproxy.route_list
    """
    raw = _send("show map /etc/haproxy/routes.map")
    routes = {}
    for line in raw.splitlines():
        # show map output format: <ptr> <key> <value>
        parts = line.split()
        if len(parts) >= 3:
            routes[parts[1]] = parts[2]
    return routes


def route_set(hostname, backend):
    """
    Add or update a hostname → backend mapping in the live routes map.

    Takes effect immediately. To persist across restarts, also update pillar
    and run: salt 'proxy*' state.apply haproxy.route

    CLI Example::

        salt 'proxy*' haproxy.route_set app.example.com app_servers
    """
    map_file = "/etc/haproxy/routes.map"
    try:
        _send("del map {} {}".format(map_file, hostname))
    except CommandExecutionError:
        pass
    _send("add map {} {} {}".format(map_file, hostname, backend))
    return "{} -> {}".format(hostname, backend)


def route_del(hostname):
    """
    Remove a hostname route from the live routes map.

    Takes effect immediately. To persist across restarts, also update pillar
    and run: salt 'proxy*' state.apply haproxy.route

    CLI Example::

        salt 'proxy*' haproxy.route_del app.example.com
    """
    _send("del map /etc/haproxy/routes.map {}".format(hostname))
    return "{} removed".format(hostname)
