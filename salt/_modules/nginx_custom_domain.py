"""
Nginx custom domain management for MediaWiki wikis.

Manages per-domain nginx server blocks stored in
/etc/nginx/conf.d/custom_domains/.  Each domain gets its own .conf file.
A JSON registry at /etc/nginx/custom_domains.json tracks metadata so that
``list`` can return full details without parsing nginx config.

nginx is config-tested and reloaded after every change.

CLI examples::

    salt '*' nginx.custom_domain.add oaklandswiki oaklandswiki.com /.well-known/acme-challenge/TOKEN TOKEN.KEY
    salt '*' nginx.custom_domain.remove oaklandswiki
    salt '*' nginx.custom_domain.list
"""

import json
import logging
import os
import re

from salt.exceptions import CommandExecutionError

log = logging.getLogger(__name__)

__pillar__ = {}
__salt__ = {}

_CONF_DIR = "/etc/nginx/conf.d/custom_domains"
_REGISTRY = "/etc/nginx/custom_domains.json"

_WIKINAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def __virtual__():
    return "nginx.custom_domain"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_wikiname(wikiname):
    if not _WIKINAME_RE.match(wikiname):
        raise CommandExecutionError(
            "Invalid wikiname '{}' — use only letters, digits, hyphens, underscores".format(
                wikiname
            )
        )


def _conf_path(wikiname):
    return os.path.join(_CONF_DIR, "{}.conf".format(wikiname))


def _render_conf(wikiname, url, path, response):
    return (
        "# salt managed, do not modify manually\n"
        "server {{\n"
        "    listen 80;\n"
        "    server_name {url};\n"
        "\n"
        '    set $custom_domain_sitemap "{wikiname}";\n'
        "    include snippets/mediawiki-common.conf;\n"
        "\n"
        "    location = {path} {{\n"
        '        return 200 "{response}";\n'
        "    }}\n"
        "}}\n"
    ).format(wikiname=wikiname, url=url, path=path, response=response)


def _registry_read():
    if not os.path.isfile(_REGISTRY):
        return {}
    try:
        with open(_REGISTRY) as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return {}


def _registry_write(data):
    with open(_REGISTRY, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _nginx_reload():
    test = __salt__["cmd.run_all"]("nginx -t", python_shell=False)
    if test["retcode"] != 0:
        raise CommandExecutionError(
            "nginx config test failed:\n{}".format(
                test.get("stderr") or test.get("stdout", "")
            )
        )
    __salt__["cmd.run"]("systemctl reload nginx", python_shell=False)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def add(wikiname, url, path, response):
    """
    Add or update a custom domain server block for *wikiname*.

    :param wikiname: Short wiki identifier used as the sitemap variable
        (letters, digits, hyphens, underscores only).
    :param url: The custom domain hostname (e.g. ``oaklandswiki.com``).
    :param path: ACME challenge path
        (e.g. ``/.well-known/acme-challenge/TOKEN``).
    :param response: Full ACME challenge response string.

    CLI Example::

        salt '*' nginx.custom_domain.add oaklandswiki oaklandswiki.com /.well-known/acme-challenge/TOKEN TOKEN.KEY
    """
    _validate_wikiname(wikiname)
    os.makedirs(_CONF_DIR, exist_ok=True)

    try:
        with open(_conf_path(wikiname), "w") as fh:
            fh.write(_render_conf(wikiname, url, path, response))
    except OSError as exc:
        raise CommandExecutionError("Failed to write config: {}".format(exc))

    reg = _registry_read()
    reg[wikiname] = {"url": url, "path": path, "response": response}
    _registry_write(reg)

    _nginx_reload()
    return "Added custom domain '{}' -> {}".format(wikiname, url)


def remove(wikiname):
    """
    Remove the custom domain config for *wikiname* and reload nginx.

    CLI Example::

        salt '*' nginx.custom_domain.remove oaklandswiki
    """
    _validate_wikiname(wikiname)
    conf = _conf_path(wikiname)
    if not os.path.isfile(conf):
        raise CommandExecutionError(
            "No custom domain config found for '{}'".format(wikiname)
        )

    try:
        os.remove(conf)
    except OSError as exc:
        raise CommandExecutionError("Failed to remove config: {}".format(exc))

    reg = _registry_read()
    reg.pop(wikiname, None)
    _registry_write(reg)

    _nginx_reload()
    return "Removed custom domain '{}'".format(wikiname)


def list_():
    """
    List all managed custom domains and their metadata.

    CLI Example::

        salt '*' nginx.custom_domain.list
    """
    return _registry_read()


__func_alias__ = {"list_": "list"}