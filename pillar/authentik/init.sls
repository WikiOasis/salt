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

  # Setting this REPLACES authentik's built-in default list (private ranges +
  # loopback + link-local) rather than adding to it, so those have to be
  # repeated here alongside Cloudflare's edge ranges. Without this, the second
  # hop in X-Forwarded-For -- id.wikioasis.org resolves through Cloudflare,
  # which appends the real client IP, and then haproxy's `option forwardfor`
  # appends its own peer address (a Cloudflare edge IP) on top -- has no
  # trusted proxy behind it, so authentik stops peeling the chain at that edge
  # IP and logs it as the client instead of the actual visitor.
  #
  # IPv4/IPv6 ranges below are Cloudflare's published edge list
  # (https://www.cloudflare.com/ips-v4, https://www.cloudflare.com/ips-v6,
  # checked 2026-09-03). These change rarely but not never -- re-diff against
  # that page if authentik's event log starts showing Cloudflare IPs as the
  # client again.
  trusted_proxy_cidrs:
    - 127.0.0.0/8
    - 10.0.0.0/8
    - 172.16.0.0/12
    - 192.168.0.0/16
    - fe80::/10
    - ::1/128
    # Cloudflare IPv4
    - 173.245.48.0/20
    - 103.21.244.0/22
    - 103.22.200.0/22
    - 103.31.4.0/22
    - 141.101.64.0/18
    - 108.162.192.0/18
    - 190.93.240.0/20
    - 188.114.96.0/20
    - 197.234.240.0/22
    - 198.41.128.0/17
    - 162.158.0.0/15
    - 104.16.0.0/13
    - 104.24.0.0/14
    - 172.64.0.0/13
    - 131.0.72.0/22
    # Cloudflare IPv6
    - 2400:cb00::/32
    - 2606:4700::/32
    - 2803:f800::/32
    - 2405:b500::/32
    - 2405:8100::/32
    - 2a06:98c0::/29
    - 2c0f:f248::/32

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
