# Common NRPE check plugins — apply to all monitored hosts via top.sls.
# Requires: nagios-nrpe-server already installed on target.

/usr/lib/nagios/plugins/check_mem.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_mem.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/mem.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/mem.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_mem.sh
    - watch_in:
      - service: nagios-nrpe-server
