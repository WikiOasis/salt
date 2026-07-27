# mwdeploy-shim — ships to every minion the deploy portal can reach: staging,
# every mw*/task* appserver, every proxy*. See ../../../docs mirrored from
# https://github.com/WikiOasis/mw-deploy/blob/main/docs/SALT-INTEGRATION.md
#
# Vendored from mw-deploy's shim/mwdeploy_shim.py rather than pulled via gitfs —
# keep salt/mwdeploy/files/mwdeploy_shim.py in sync with upstream by hand; a
# divergent shim across the fleet is a debugging nightmare, so bump the VERSION
# comment below whenever you re-vendor.

# Vendored upstream version: 2.1.0 (wikioasis/mw-deploy shim/mwdeploy_shim.py)
{%- set shim_version = '2.1.0' %}

mwdeploy-shim-deps:
  pkg.installed:
    - pkgs:
      - git
      - rsync
      - patch
      - curl
      - python3

/usr/local/bin/mwdeploy-shim:
  file.managed:
    - source: salt://mwdeploy/files/mwdeploy_shim.py
    - mode: '0755'
    - user: root
    - group: root
    - require:
      - pkg: mwdeploy-shim-deps

# A minion left on a stale shim fails the portal's import screen with an
# argparse usage error instead of anything self-explanatory, so a version
# mismatch here is a hard highstate failure, not a warning.
mwdeploy-shim-verify:
  cmd.run:
    - name: >-
        test "$(/usr/local/bin/mwdeploy-shim --version)" = "mwdeploy-shim {{ shim_version }}"
    - require:
      - file: /usr/local/bin/mwdeploy-shim

# The shim runs git/rsync/patch/php as the web user so files land owned
# correctly, then re-asserts ownership with chown as root. If the minion runs
# as www-data already, cmd_current_user() in the shim skips the wrapper and
# these rules go unused, but they are harmless either way.
/etc/sudoers.d/mwdeploy:
  file.managed:
    - user: root
    - group: root
    - mode: '0440'
    # A syntactically broken sudoers file locks everyone out of sudo on the box.
    - check_cmd: /usr/sbin/visudo -c -f
    - contents: |
        Defaults!/usr/local/bin/mwdeploy-shim !requiretty
        root ALL=(www-data) NOPASSWD: /usr/bin/git, /usr/bin/rsync, /usr/bin/patch, /usr/bin/php, /bin/mkdir
        root ALL=(root)     NOPASSWD: /bin/chown
    - require:
      - file: /usr/local/bin/mwdeploy-shim
