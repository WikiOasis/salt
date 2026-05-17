# HAProxy NRPE checks — apply to proxy* servers via top.sls.
# Requires: socat, nagios-nrpe-server already installed on target.
# HAProxy stats socket must be accessible to the nagios user — add to haproxy group:

nagios_in_haproxy_group:
  user.present:
    - name: nagios
    - groups:
      - haproxy
    - remove_groups: False

/usr/lib/nagios/plugins/check_haproxy.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_haproxy.sh
    - mode: '0755'
    - user: root
    - group: root

/usr/lib/nagios/plugins/check_haproxy_backends.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_haproxy_backends.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/haproxy.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/haproxy.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_haproxy.sh
      - file: /usr/lib/nagios/plugins/check_haproxy_backends.sh
    - watch_in:
      - service: nagios-nrpe-server
