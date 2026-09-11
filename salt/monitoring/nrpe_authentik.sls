# authentik NRPE checks — apply to auth* servers via top.sls.
# Requires: nagios-nrpe-server and check_systemd_service.sh already on target
# (deployed by monitoring.nrpe and monitoring.nrpe_salt, which run everywhere).
#
# Two checks, because they fail in different ways and the difference is the
# first thing worth knowing:
#
#   check_authentik       the readiness endpoint through the published port —
#                         the end-to-end signal, and what actually correlates
#                         with id.wikioasis.org being usable.
#   check_authentik_unit  the systemd unit. The unit is Type=oneshot, so this
#                         going CRITICAL means the stack was never brought up
#                         (or was stopped by hand); the containers themselves
#                         are supervised by dockerd, not by systemd, so this
#                         can sit OK while every container is crash-looping.
#                         That is exactly why the first check exists.
#   check_authentik_backup        a dump ran in the last 26/28h.
#   check_authentik_backup_upload that dump reached S3. Reports OK rather than
#                         CRITICAL when no bucket is configured, since keeping
#                         dumps locally is a supported configuration.
#
# The two backup checks are what stop "we have backups" quietly becoming "we
# had backups" — the cron's only output is a file nobody reads.

# The two backup checks read root-only paths: the dump marker under
# /srv/authentik/backups (0700 root:root, inside /srv/authentik at 0750
# root:root) and /etc/authentik-backup/s3.env, which holds S3 credentials.
# NRPE runs plugins as the unprivileged nagios user, which is in no group that
# can traverse either, so before this grant the dump check reported "has never
# succeeded" whether or not a dump ran, and the upload check could not see a
# configured bucket and short-circuited to a false OK. Granting sudo on this one
# script keeps the dumps and the credentials root-only, which is the point of
# their modes.
#
# The grant pins both arguments. The script takes its state directory from $2
# and then reads "$STATE_DIR/last_backup" as root, so a rule with no argument
# spec -- which in sudoers permits ANY arguments -- would let anything running
# as nagios have root stat and read a file of that name anywhere on the box.
# Two commands on one rule, comma-separated, and nothing else.
#
# Those two strings have to match nrpe.d/authentik.cfg character for character
# or sudo refuses and the checks break, so backup_path is derived here exactly
# as monitoring/files/nrpe/authentik.cfg.jinja derives it. Change one, change
# the other.
#
# Nothing else in the tree installs sudo (users/init.sls only adds people to the
# sudo group and writes files into /etc/sudoers.d), and visudo below ships with
# it, so pin the package here rather than let the grant be silently inert.
{%- set p = salt['pillar.get']('authentik', {}) %}
{%- set backup = p.get('backup', {}) %}
{%- set backup_path = backup.get('path', p.get('path', '/srv/authentik') ~ '/backups') %}
sudo:
  pkg.installed

/etc/sudoers.d/nagios-authentik-backup:
  file.managed:
    - contents: |
        nagios ALL=(root) NOPASSWD: /usr/lib/nagios/plugins/check_authentik_backup.sh dump {{ backup_path }}, /usr/lib/nagios/plugins/check_authentik_backup.sh upload {{ backup_path }}
    - mode: '0440'
    - user: root
    - group: root
    # A syntactically broken sudoers file locks everyone out of sudo on the box.
    - check_cmd: /usr/sbin/visudo -c -f
    - require:
      - pkg: sudo

/usr/lib/nagios/plugins/check_authentik.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_authentik.sh
    - mode: '0755'
    - user: root
    - group: root

/usr/lib/nagios/plugins/check_authentik_backup.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_authentik_backup.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/authentik.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/authentik.cfg.jinja
    - template: jinja
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_authentik.sh
      - file: /usr/lib/nagios/plugins/check_authentik_backup.sh
      - file: /usr/lib/nagios/plugins/check_systemd_service.sh
      - file: /etc/sudoers.d/nagios-authentik-backup
    - watch_in:
      - service: nagios-nrpe-server
