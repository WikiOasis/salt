# authentik (https://goauthentik.io) -- the central identity provider, on
# auth-us-east-021. Reached at https://id.wikioasis.org through Cloudflare ->
# proxy-us-east-021 (the `authentik` backend in pillar/haproxy) -> this host.
# Non-secret configuration is in pillar/authentik; the signing key, the database
# password and the optional first-boot admin credentials are in pillar/private.
#
# No LDAP, deliberately. authentik keeps its own user store in Postgres and is a
# complete IdP on its own -- OIDC, SAML, proxy providers, MFA, flows. LDAP only
# enters the picture to federate *from* an existing directory (an LDAP source),
# or to serve LDAP *to* an application that can speak nothing else (an LDAP
# outpost). Neither applies here, so there is no slapd and no second directory
# to keep in sync. Either can be added later without moving anything.
#
# Docker, not packages: authentik ships no distribution package and upstream
# supports only Compose and Kubernetes. This is the fleet's first Docker
# workload and its first Postgres, and both are confined to this host's Compose
# project rather than becoming fleet-wide roles -- nothing else needs them, and
# an identity store is the last thing that should share a database server.
#
# Three services: postgresql, server, worker. There is no Redis -- authentik
# dropped that dependency, and the upstream Compose file for the pinned version
# no longer ships one.

{%- set p = salt['pillar.get']('authentik', {}) %}
{%- set path = p.get('path', '/srv/authentik') %}
{%- set http_port = p.get('http_port', 9000) %}
{%- set backup = p.get('backup', {}) %}
{%- set backup_path = backup.get('path', path ~ '/backups') %}
{#- Same derivation as docker-compose.yml.jinja: the published ports are on the
    vrack address, so the health poll below has to ask for them there rather
    than on localhost. #}
{%- set private_ips = salt['network.ip_addrs'](cidr='10.0.0.0/8') %}
{%- set bind = p.get('bind_address') or (private_ips[0] if private_ips else '127.0.0.1') %}

# Both packages are in Debian 13, so this needs no third-party apt repository --
# nothing else in the fleet has one, and base owns /etc/apt/sources.list
# outright, which would fight anything dropped in beside it. curl is for the
# readiness poll below and for the NRPE check in monitoring.nrpe_authentik.
#
# `docker-compose` here is NOT Compose v1. Debian ships Compose v2 under the
# plain name (2.26.1 in trixie, from the Go rewrite) and has no
# `docker-compose-v2` package at all -- that name is Ubuntu's. The package
# installs /usr/libexec/docker/cli-plugins/docker-compose as well as
# /usr/bin/docker-compose, so `docker compose` as a subcommand works and is
# what this state uses throughout. Do not "correct" this to docker-compose-v2:
# it does not exist, and apt fails with "Unable to locate package".
authentik-packages:
  pkg.installed:
    - pkgs:
      - docker.io
      - docker-compose
      - curl

{%- if p.get('registry_proxy', {}).get('enabled', True) %}
# Must exist before dockerd starts, or the first pull is the one that fails.
# See the file's own header for why an HTTP proxy is involved at all.
/etc/systemd/system/docker.service.d:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'
    - makedirs: True
    - require:
      - pkg: authentik-packages

/etc/systemd/system/docker.service.d/http-proxy.conf:
  file.managed:
    - source: salt://authentik/files/docker-http-proxy.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - file: /etc/systemd/system/docker.service.d
{%- else %}
/etc/systemd/system/docker.service.d/http-proxy.conf:
  file.absent: []
{%- endif %}

docker:
  service.running:
    - enable: True
    - watch:
      - file: /etc/systemd/system/docker.service.d/http-proxy.conf
    - require:
      - pkg: authentik-packages

{{ path }}:
  file.directory:
    - user: root
    - group: root
    - mode: '0750'
    - makedirs: True

# Mounted read-only into the containers. Both stay empty until someone wants a
# branded login page or a certificate authentik did not generate itself; they
# exist so the Compose file can reference them unconditionally.
authentik-mount-dirs:
  file.directory:
    - names:
      - {{ path }}/custom-templates
      - {{ path }}/certs
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - file: {{ path }}

# An unset secret is not a rendering error: pillar.get falls back to '' and the
# .env below would be written with an empty AUTHENTIK_SECRET_KEY -- which
# authentik accepts at boot and then uses to sign session cookies and encrypt
# stored credentials, so the failure surfaces much later as sessions that do not
# survive anything. Fail here, where the message names the missing pillar key.
authentik-secrets:
  test.check_pillar:
    - present:
      - authentik:secret_key
      - authentik:postgres_password

{{ path }}/docker-compose.yml:
  file.managed:
    - source: salt://authentik/files/docker-compose.yml.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0640'
    - require:
      - file: {{ path }}

# Every secret the stack has: the Postgres password, the signing key, and the
# first-boot admin credentials if they are set. Compose reads it both for
# ${...} interpolation in docker-compose.yml and as each service's env_file.
{{ path }}/.env:
  file.managed:
    - source: salt://authentik/files/authentik.env.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0600'
    - show_changes: False
    - require:
      - file: {{ path }}
      - test: authentik-secrets

/etc/systemd/system/authentik.service:
  file.managed:
    - source: salt://authentik/files/authentik.service.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'

authentik:
  service.running:
    - enable: True
    - watch:
      - file: /etc/systemd/system/authentik.service
      - file: {{ path }}/docker-compose.yml
      - file: {{ path }}/.env
    - require:
      - service: docker
      - file: {{ path }}/docker-compose.yml
      - file: {{ path }}/.env
      - file: authentik-mount-dirs

# `docker compose up -d` returns as soon as the containers are created, so
# without this the highstate goes green while the stack is still migrating --
# or has already crash-looped on a bad image tag or a rejected database
# password, with the only outward symptom a 503 from haproxy. Poll the
# readiness endpoint instead and fail here, where the message says what to
# read next. Only on change, so a no-op highstate costs nothing.
authentik-ready:
  cmd.run:
    - name: |
        for _ in $(seq 1 60); do
          code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
            http://{{ bind }}:{{ http_port }}/-/health/ready/ || true)
          case "$code" in
            2??) echo "authentik ready (HTTP $code)"; exit 0 ;;
          esac
          sleep 5
        done
        echo "authentik was not ready within 300s (last HTTP status: ${code:-none})."
        echo "Check: journalctl -u authentik -n 50"
        echo "       docker compose -f {{ path }}/docker-compose.yml logs --tail 50"
        exit 1
    - onchanges:
      - service: authentik
    - require:
      - pkg: authentik-packages
{%- if backup.get('enabled', True) %}

{{ backup_path }}:
  file.directory:
    - user: root
    - group: root
    - mode: '0700'
    - makedirs: True
    - require:
      - file: {{ path }}

# The Postgres volume IS the identity store: every account, group, application,
# certificate and MFA enrolment. Nothing else in the fleet would back it up --
# mariadb.backup only knows about MariaDB on db* -- so a nightly pg_dump lands
# here and is then uploaded to OVHcloud Object Storage.
#
# Both halves matter and they cover different failures. The local copy is the
# fast restore for what actually goes wrong week to week: a bad upgrade, a
# botched blueprint import, a deleted application. The remote copy is the one
# that survives losing this host, which is the failure a backup sitting on the
# same disk as its database does nothing about. Local retention is therefore
# deliberately shorter than the bucket's.
#
# With authentik:backup:s3:bucket unset the local dump still runs and the
# upload is skipped -- a supported configuration, and one the
# check_authentik_backup_upload check reports as OK rather than failing.
# awscli and jq only matter to the backup, so they are installed with it rather
# than in the main package list. Same apt packages mariadb.backup uses.
authentik-backup-packages:
  pkg.installed:
    - pkgs:
      - awscli
      - jq

/etc/authentik-backup:
  file.directory:
    - user: root
    - group: root
    - mode: '0750'

# Bucket, endpoint, prefix and storage class. Sourced by both scripts with
# `set -a`, so the AWS_* names in it configure the CLI as well.
/etc/authentik-backup/s3.env:
  file.managed:
    - source: salt://authentik/files/authentik-backup-s3.env.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0640'
    - require:
      - file: /etc/authentik-backup

/etc/authentik-backup/credentials:
  file.managed:
    - source: salt://authentik/files/authentik-backup-credentials.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0600'
    # An S3 key with write access to the bucket holding every identity dump.
    - show_changes: False
    - require:
      - file: /etc/authentik-backup

/etc/authentik-backup/aws.conf:
  file.managed:
    - source: salt://authentik/files/authentik-backup-aws.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0640'
    - require:
      - file: /etc/authentik-backup

/etc/authentik-backup/lifecycle.json:
  file.managed:
    - source: salt://authentik/files/authentik-backup-lifecycle.json.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0640'
    - require:
      - file: /etc/authentik-backup

/usr/local/sbin/authentik-backup-s3-init:
  file.managed:
    - source: salt://authentik/files/authentik-backup-s3-init.sh
    - user: root
    - group: root
    - mode: '0750'

# Verifies the bucket is reachable on every apply, so a wrong endpoint, a
# mistyped bucket name or a revoked key fails the highstate here rather than at
# 03:30 in a cron job whose output nobody reads. Applies the lifecycle policy
# only when authentik:backup:s3:manage_lifecycle is true -- see the warning in
# authentik-backup-lifecycle.json.jinja about what enabling that does to a
# bucket shared with mariadb.backup.
authentik-backup-s3-init:
  cmd.run:
    - name: /usr/local/sbin/authentik-backup-s3-init
    - unless: /usr/local/sbin/authentik-backup-s3-init --check
    - require:
      - pkg: authentik-backup-packages
      - file: /usr/local/sbin/authentik-backup-s3-init
      - file: /etc/authentik-backup/s3.env
      - file: /etc/authentik-backup/credentials
      - file: /etc/authentik-backup/aws.conf
      - file: /etc/authentik-backup/lifecycle.json

/usr/local/sbin/authentik-backup:
  file.managed:
    - source: salt://authentik/files/authentik-backup.sh.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0750'
    - require:
      - pkg: authentik-backup-packages
      - file: /etc/authentik-backup/s3.env

# Truncating redirect (`>`), not appending: one run a night, and the only
# output anybody wants is the last one's. An append here would be a log file
# nothing rotates.
authentik-backup-cron:
  cron.present:
    - name: /usr/local/sbin/authentik-backup > /var/log/authentik-backup.log 2>&1
    - user: root
    - hour: '{{ backup.get('hour', '3') }}'
    - minute: '{{ backup.get('minute', '30') }}'
    - identifier: authentik-backup
    # Deliberately NOT dependent on authentik-backup-s3-init. A wrong bucket
    # name or a revoked key fails that state and reddens the highstate, which
    # is the point of it -- but it must not also cost us the local dump. The
    # cron installs either way, the nightly upload fails loudly, and
    # check_authentik_backup_upload is what says so.
    - require:
      - file: /usr/local/sbin/authentik-backup
      - file: {{ backup_path }}
{%- endif %}
