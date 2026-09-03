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
