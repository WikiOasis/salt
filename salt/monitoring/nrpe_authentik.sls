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
    - watch_in:
      - service: nagios-nrpe-server
