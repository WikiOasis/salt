/etc/nagios/nrpe.d/sal_server.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/sal_server.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_systemd_service.sh
    - watch_in:
      - service: nagios-nrpe-server

/usr/lib/nagios/plugins/check_sal_backlog.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_sal_backlog.sh
    - mode: '0755'
