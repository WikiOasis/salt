authentik:
  path: /srv/authentik
  domain: id.wikioasis.org
  version: 2026.8.1
  image: ghcr.io/goauthentik/server
  postgres_image: docker.io/library/postgres:16-alpine
  db:
    name: authentik
    user: authentik

  http_port: 9000
  https_port: 9443
  metrics_port: 9300

  bind_address: ''

  # dockerd needs an HTTP proxy to pull images: these VMs have no IPv4 egress
  # (metal/ip_forwarding does inbound DNAT only, with no MASQUERADE), and
  # ghcr.io publishes no AAAA record, so the public IPv6 from metal.vm_ipv6
  # cannot reach it. This points dockerd at the squid already running on the
  # VM's own metal host, derived from proxmox:vms -> metal_host -> dns_hosts.
  #
  # Set enabled: false if the metal hosts ever get a MASQUERADE rule and VMs
  # have real IPv4 egress. Verify which world you are in from the auth box:
  #   curl -4 -sS -o /dev/null -w '%{http_code}\n' --max-time 10 https://ghcr.io/v2/
  # 401 means direct IPv4 works and the proxy is redundant; a timeout means it
  # is required.
  registry_proxy:
    enabled: true
    port: 3129
    # url: http://10.0.2.1:3129   # override the derivation outright
    no_proxy: localhost,127.0.0.1,10.0.0.0/8,.ovvin.wonet

  log_level: info
  error_reporting: false
  disable_analytics: true
  disable_update_check: false

  log:
    max_size: 50m
    max_file: 3

  email:
    host: smtp.gmail.com
    port: 465
    username: noreply@wikioasis.org
    use_tls: false
    use_ssl: true
    timeout: 10
    from: id@wikioasis.org

  backup:
    enabled: true
    path: /srv/authentik/backups
    retain_days: 14
    hour: '3'
    minute: '30'

    s3:
      bucket: wikioasis-backups
      region: us-east-va
      prefix: authentik
      storage_class: STANDARD_IA

      manage_lifecycle: false
      lifecycle:
        expire_days: 90
        min_storage_days: 30
        abort_incomplete_multipart_days: 7
