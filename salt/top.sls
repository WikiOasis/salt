base:
  '*':
    - users
  'metal*':
    - metal
  'proxy*':
    - haproxy
  '*-us-east-0[0-9][0-9]':
    - metal.vm_ipv6
