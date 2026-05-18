# Salt-minion NRPE check — apply to all servers via top.sls.
# Requires: nagios-nrpe-server already installed on target.

/usr/lib/nagios/plugins/check_systemd_service.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_systemd_service.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/salt_minion.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/salt_minion.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_systemd_service.sh
    - watch_in:
      - service: nagios-nrpe-server
