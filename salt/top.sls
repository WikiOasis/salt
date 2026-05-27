base:
  '*':
    - base
    - users
    - monitoring.nrpe
    - monitoring.nrpe_common
    - monitoring.nrpe_salt
    - monitoring.node_exporter
  'apps*':
    - php
    - nginx
    - monitoring.nrpe_nginx
    - monitoring.nrpe_php
  'db*':
    - mariadb
    - mariadb.monitoring_user
    - mariadb.prometheus_user
    - mariadb.backup
    - mariadb.nrpe_backup
    - monitoring.mysqld_exporter
  'metal*':
    - metal
    - monitoring.nrpe_metal
  'proxy*':
    - haproxy
    - monitoring.nrpe_haproxy
    - monitoring.haproxy_exporter
    - mediawiki.proxy
  'monitoring*':
    - monitoring
    - monitoring.director
    - monitoring.nrpe_nginx
    - monitoring.prometheus
    - monitoring.grafana
    - monitoring.statsd_exporter
  'staging*':
    - mediawiki

  'mw*':
    - mediawiki.target

  'mw* or staging*':
    - match: compound
    - php
    - nginx
    - sentry_relay
    - monitoring.nrpe_nginx
    - monitoring.nrpe_php
    - monitoring.nrpe_mediawiki
  'redis*':
    - redis
    - monitoring.nrpe_redis
    - monitoring.redis_exporter
  'salt*':
    - monitoring.nrpe_salt_master
  '*-us-east-0[0-9][0-9]*':
    - metal.vm_ipv6
