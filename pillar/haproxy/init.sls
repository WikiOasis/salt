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
    - hostname: grafana.wikioasis.org
      backend: grafana
      active: true
    - hostname: zep.wikioasis.org
      backend: zep
      active: true
    - hostname: zep-api.wikioasis.org
      backend: zep-api
      active: true

  frontends:
    http:
      bind: '*:80'
      mode: http
      use_routes: true
      persistent_hosts:
        - hostname: icinga.wikioasis.org
          backend: icinga
        - hostname: grafana.wikioasis.org
          backend: grafana
        - hostname: test.wikioasis.org
          backend: staging
        - hostname: phorge.wikioasis.org
          backend: apps
        - hostname: phorge.wikioasisusercontent.net
          backend: apps
        - hostname: safety.wikioasis.org
          backend: apps
      default_backend: mediawiki
      options:
        - forwardfor
        - http-server-close

  backends:
    apps:
      balance: roundrobin
      options:
        - forwardfor
      servers:
        - name: apps-us-east-021
          host: apps-us-east-021.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
    mediawiki:
      balance: roundrobin
      options:
        - forwardfor
        - httpchk GET /wiki/Main_Page HTTP/1.1\r\nHost:\ wikioasis.org
      http_check: expect str wikioasis
      servers:
        - name: mw-us-east-011
          host: mw-us-east-011.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
        - name: mw-us-east-012
          host: mw-us-east-012.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
        - name: mw-us-east-021
          host: mw-us-east-021.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
        - name: mw-us-east-022
          host: mw-us-east-022.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
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
    grafana:
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
    staging:
      balance: roundrobin
      options:
        - forwardfor
      servers:
        - name: staging-us-east-021
          host: staging-us-east-021.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
    zep:
      balance: roundrobin
      options:
        - forwardfor
      servers:
        - name: apps-us-east-021
          host: apps-us-east-021.ovvin.wonet
          port: 3001
          check: true
          weight: 1
          depooled: false
    zep-api:
      balance: roundrobin
      options:
        - forwardfor
      servers:
        - name: apps-us-east-021
          host: apps-us-east-021.ovvin.wonet
          port: 3002
          check: true
          weight: 1
          depooled: false
