# OpenSearch NRPE check — apply to opensearch* servers via top.sls.
# Requires: nagios-nrpe-server and opensearch already installed on target.

/usr/lib/nagios/plugins/check_opensearch.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_opensearch.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/opensearch.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/opensearch.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_opensearch.sh
    - watch_in:
      - service: nagios-nrpe-server