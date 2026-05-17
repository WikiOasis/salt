base:
  '*':
    - base
    - users
  'db*':
    - mariadb
  'metal*':
    - metal
  'proxy*':
    - haproxy
    - monitoring.nrpe_haproxy
  'monitoring*':
    - monitoring
    - monitoring.director
    - monitoring.nrpe_nginx
  '*-us-east-0[0-9][0-9]*':
    - metal.vm_ipv6
    - monitoring.nrpe
    - monitoring.nrpe_common
