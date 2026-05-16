base:
  '*':
    - users
  'metal*':
    - metal.ip_forwarding
    - metal.ssh
    - dns-dhcp
  'proxy*':
    - haproxy
