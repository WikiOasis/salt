haproxy:
  global:
    maxconn: 4096
    log: /dev/log local0 info

  defaults:
    mode: http
    timeout_connect: 5s
    timeout_client: 50s
    timeout_server: 50s

  # Path to the HAProxy stats/runtime socket — required for depool/repool/route/status
  stats_socket: /run/haproxy/admin.sock

  # Hostname → backend routing map (managed by haproxy.route)
  # Entries with active: false are removed from the map
  routes:
    - hostname: app.example.com
      backend: app_servers
      active: true
    - hostname: api.example.com
      backend: api_servers
      active: true

  frontends:
    http:
      bind: '*:80'
      mode: http
      # use_routes: true wires this frontend to the routes map above.
      # Requests whose Host header matches a route entry are sent to that backend.
      # All other requests fall through to default_backend.
      use_routes: true
      default_backend: app_servers
      options:
        - forwardfor
        - http-server-close

  backends:
    app_servers:
      balance: roundrobin
      options:
        - forwardfor
        - httpchk GET /health
      servers:
        - name: app01
          host: 192.168.1.10
          port: 8080
          check: true
          weight: 1
          depooled: false
        - name: app02
          host: 192.168.1.11
          port: 8080
          check: true
          weight: 1
          depooled: false

    api_servers:
      balance: roundrobin
      options:
        - forwardfor
        - httpchk GET /api/health
      servers:
        - name: api01
          host: 192.168.1.20
          port: 9090
          check: true
          weight: 1
          depooled: false
        - name: api02
          host: 192.168.1.21
          port: 9090
          check: true
          weight: 1
          depooled: false