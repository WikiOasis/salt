haproxy:
  global:
    maxconn: 4096
    log: /dev/log local0 info

  defaults:
    mode: http
    timeout_connect: 5s
    timeout_client: 50s
    timeout_server: 50s

  stats_socket: /run/haproxy/admin.sock

  routes:
    - hostname: icinga.wikioasis.org
      backend: icinga
      active: true

  frontends:
    http:
      bind: '*:80'
      mode: http
      use_routes: true
      persistent_hosts:
        - hostname: icinga.wikioasis.org
          backend: icinga
      default_backend: icinga
      options:
        - forwardfor
        - http-server-close

  backends:
    icinga:
      balance: roundrobin
      options:
        - forwardfor
      servers:
        - name: monitoring-us-east-021
          host: monitoring-us-east-021.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
