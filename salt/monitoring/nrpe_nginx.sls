# Nginx error rate NRPE check — apply to servers with nginx via top.sls.
# Requires: nagios-nrpe-server already installed on target.
# Nagios user needs read access to /var/log/nginx/ — added to adm group.

nagios_in_adm_group:
  user.present:
    - name: nagios
    - groups:
      - adm
    - remove_groups: False

/usr/lib/nagios/plugins/check_nginx_errors.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_nginx_errors.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/nginx.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/nginx.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_nginx_errors.sh
    - watch_in:
      - service: nagios-nrpe-server
