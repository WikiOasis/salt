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
  'monitoring*':
    - monitoring
    - monitoring.director
  '*-us-east-0[0-9][0-9]*':
    - metal.vm_ipv6
    - monitoring.nrpe
