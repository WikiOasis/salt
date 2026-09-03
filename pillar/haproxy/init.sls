haproxy:
  global:
    maxconn: 4096
    log: /dev/log local0 info

  defaults:
    mode: http
    timeout_connect: 5s
    timeout_client: 50s
    timeout_server: 1200s

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
    - hostname: id.wikioasis.org
      backend: authentik
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
        - hostname: portal.wikioasis.org
          backend: apps
        - hostname: console.wikioasis.org
          backend: deploy_portal
        - hostname: id.wikioasis.org
          backend: authentik
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
        - name: apps-us-east-021.ovvin.wonet
          host: apps-us-east-021.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
    mediawiki:
      balance: roundrobin
      options:
        - forwardfor
        - httpchk
      http_checks:
        - send meth GET uri /wiki/Main_Page ver HTTP/1.1 hdr Host wikioasis.org
        - expect string wikioasis
      servers:
        - name: mw-us-east-011.ovvin.wonet
          host: mw-us-east-011.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
        - name: mw-us-east-012.ovvin.wonet
          host: mw-us-east-012.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
        - name: mw-us-east-021.ovvin.wonet
          host: mw-us-east-021.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
        - name: mw-us-east-022.ovvin.wonet
          host: mw-us-east-022.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
    # Deliberately NOT in the mediawiki backend: a rollout depools servers from
    # that backend, and depooling the box serving this portal would take the
    # dashboard down mid-deploy.
    deploy_portal:
      balance: roundrobin
      options:
        - forwardfor
        - httpchk
      http_checks:
        - send meth GET uri /up
        - expect status 200
      # A deployment's live dashboard holds a websocket open for the length of
      # a rollout (tens of minutes); the default tunnel/server timeouts would
      # drop it and silently degrade the dashboard to polling.
      timeout_tunnel: 1h
      timeout_server: 120s
      http_request:
        - set-header X-Forwarded-Proto https
        - set-header X-Forwarded-Port 443
      servers:
        - name: salt-us-east-021.ovvin.wonet
          host: salt-us-east-021.ovvin.wonet
          port: 80
          check: true
          weight: 1
          depooled: false
    # The identity provider (salt/authentik on auth-us-east-021). Everything
    # that logs in through id.wikioasis.org comes through here, so it is its
    # own backend and shares a server with nothing.
    authentik:
      balance: roundrobin
      options:
        - forwardfor
        - httpchk
      # /-/health/live/ is the shallow endpoint on purpose. It answers as soon
      # as the server process is up, which is the right question for "may this
      # backend take traffic". Readiness — database reachable, migrations done
      # — is checked by Icinga over NRPE instead, where a failure pages someone
      # rather than depooling the only server and turning every login into a
      # 503.
      #
      # rstatus, not status: authentik answers these with 204, and a release
      # that moved to 200 would take the IdP down on a technicality.
      #
      # ver/hdr are both spelled out because `http-check send` defaults to
      # HTTP/1.0 with NO Host header, and this check should look like the
      # traffic it is standing in for -- everything real arrives from
      # Cloudflare with a Host. It also keeps the check honest against a Go
      # HTTP server, which is entitled to reject an HTTP/1.1 request that has
      # no Host at all. Same reason the mediawiki backend spells them out.
      http_checks:
        - send meth GET uri /-/health/live/ ver HTTP/1.1 hdr Host id.wikioasis.org
        - expect rstatus ^2
      # authentik builds absolute URLs from the forwarded scheme — the OIDC
      # issuer and discovery document, SAML endpoints, every redirect_uri it
      # checks. Without these it advertises http://, which fails the strict
      # scheme comparison in most OAuth clients, and its session cookies lose
      # Secure.
      http_request:
        - set-header X-Forwarded-Proto https
        - set-header X-Forwarded-Port 443
      # The admin interface and any future outpost hold websockets open; the
      # default tunnel timeout would drop them. Same reason deploy_portal has
      # one.
      timeout_tunnel: 1h
      servers:
        - name: auth-us-east-021.ovvin.wonet
          host: auth-us-east-021.ovvin.wonet
          port: 9000
          check: true
          weight: 1
          depooled: false
    icinga:
      balance: roundrobin
      options:
        - forwardfor
      servers:
        - name: monitoring-us-east-021.ovvin.wonet
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
        - name: monitoring-us-east-021.ovvin.wonet
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
        - name: staging-us-east-021.ovvin.wonet
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
        - name: apps-us-east-021.ovvin.wonet
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
        - name: apps-us-east-021.ovvin.wonet
          host: apps-us-east-021.ovvin.wonet
          port: 3002
          check: true
          weight: 1
          depooled: false
