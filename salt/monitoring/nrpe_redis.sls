# Redis NRPE check — apply to redis* servers via top.sls.
# Requires: nagios-nrpe-server and redis-server already installed on target.

/usr/lib/nagios/plugins/check_redis.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_redis.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/redis.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/redis.cfg.jinja
    - template: jinja
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_redis.sh
    - watch_in:
      - service: nagios-nrpe-server
