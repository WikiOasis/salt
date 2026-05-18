# Salt-master NRPE check — apply to salt* servers via top.sls.
# Requires: nagios-nrpe-server and check_systemd_service.sh already on target
# (deployed by monitoring.nrpe_salt which runs on all hosts).

/etc/nagios/nrpe.d/salt_master.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/salt_master.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_systemd_service.sh
    - watch_in:
      - service: nagios-nrpe-server
