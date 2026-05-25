base:
  '*':
    - base
    - users
    - monitoring.nrpe
    - monitoring.nrpe_common
    - monitoring.nrpe_salt
  'db*':
    - mariadb
    - mariadb.monitoring_user
  'metal*':
    - metal
    - monitoring.nrpe_metal
  'proxy*':
    - haproxy
    - monitoring.nrpe_haproxy
  'monitoring*':
    - monitoring
    - monitoring.director
    - monitoring.nrpe_nginx
  'mw* or staging*':
    - match: compound
    - php
    - nginx
    - monitoring.nrpe_nginx
    - monitoring.nrpe_php
    - monitoring.nrpe_mediawiki
  'redis*':
    - redis
    - monitoring.nrpe_redis
  'salt*':
    - monitoring.nrpe_salt_master
  '*-us-east-0[0-9][0-9]*':
    - metal.vm_ipv6
