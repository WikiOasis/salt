/usr/lib/nagios/plugins/check_mediawiki.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_mediawiki.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/mediawiki.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/mediawiki.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_mediawiki.sh
    - watch_in:
      - service: nagios-nrpe-server
