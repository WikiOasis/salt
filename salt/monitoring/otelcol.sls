# OpenTelemetry Collector (contrib) scrapes journald (all units) and nginx logs
# and pushes them directly to Sentry over OTLP/HTTP. nginx and journald use
# separate Sentry DSNs and each record is tagged with its unit/system.

{%- set otel_version = '0.153.0' %}
{%- set arch = 'arm64' if grains['cpuarch'] in ['aarch64', 'arm64'] else 'amd64' %}

# ── Remove the previous Vector-based shipper (superseded by the collector) ──────

vector_service_stopped:
  service.dead:
    - name: vector
    - enable: False
    - onlyif: test -f /etc/systemd/system/vector.service

vector_unit_absent:
  file.absent:
    - name: /etc/systemd/system/vector.service
    - require:
      - service: vector_service_stopped

vector_daemon_reload:
  cmd.run:
    - name: systemctl daemon-reload
    - onchanges:
      - file: vector_unit_absent

{%- for path in ['/opt/vector', '/etc/vector', '/var/lib/vector', '/usr/local/bin/vector'] %}
vector_path_absent_{{ loop.index }}:
  file.absent:
    - name: {{ path }}
    - require:
      - service: vector_service_stopped
{%- endfor %}

vector_user_absent:
  user.absent:
    - name: vector
    - require:
      - service: vector_service_stopped

otelcol_user:
  user.present:
    - name: otelcol
    - system: True
    - shell: /usr/sbin/nologin
    - home: /var/lib/otelcol
    - createhome: False
    # systemd-journal: read the journal. adm: read /var/log/nginx/*.log.
    - groups:
      - systemd-journal
      - adm

/var/lib/otelcol:
  file.directory:
    - user: otelcol
    - group: otelcol
    - mode: '0750'
    - require:
      - user: otelcol_user

/etc/otelcol:
  file.directory:
    - user: root
    - group: otelcol
    - mode: '0750'
    - require:
      - user: otelcol_user

otelcol_binary:
  archive.extracted:
    - name: /opt/otelcol-contrib
    - source: https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v{{ otel_version }}/otelcol-contrib_{{ otel_version }}_linux_{{ arch }}.tar.gz
    - source_hash: https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v{{ otel_version }}/opentelemetry-collector-releases_otelcol-contrib_checksums.txt
    - archive_format: tar
    - enforce_toplevel: False
    - if_missing: /opt/otelcol-contrib/otelcol-contrib

/usr/local/bin/otelcol-contrib:
  file.symlink:
    - target: /opt/otelcol-contrib/otelcol-contrib
    - require:
      - archive: otelcol_binary

/etc/otelcol/config.yaml:
  file.managed:
    - source: salt://monitoring/files/otelcol/config.yaml.jinja
    - template: jinja
    - user: root
    - group: otelcol
    - mode: '0640'
    - require:
      - file: /etc/otelcol

/etc/systemd/system/otelcol.service:
  file.managed:
    - contents: |
        [Unit]
        Description=OpenTelemetry Collector (Sentry log shipper)
        After=network-online.target
        Wants=network-online.target

        [Service]
        User=otelcol
        Group=otelcol
        ExecStart=/usr/local/bin/otelcol-contrib --config /etc/otelcol/config.yaml
        Restart=on-failure
        RestartSec=5

        [Install]
        WantedBy=multi-user.target
    - user: root
    - group: root
    - mode: '0644'

otelcol:
  service.running:
    - enable: True
    - watch:
      - file: /etc/otelcol/config.yaml
      - file: /etc/systemd/system/otelcol.service
    - require:
      - file: /usr/local/bin/otelcol-contrib
      - file: /etc/otelcol/config.yaml
      - file: /var/lib/otelcol
      - file: /etc/systemd/system/otelcol.service
      - user: otelcol_user

# ── journald retention ─────────────────────────────────────────────────────────
# The journal is shipped to Sentry, so cap what persists locally. Tune these to
# taste; recent logs are still kept on-disk for live on-host debugging.

/etc/systemd/journald.conf.d:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'
    - makedirs: True

/etc/systemd/journald.conf.d/90-sentry-retention.conf:
  file.managed:
    - user: root
    - group: root
    - mode: '0644'
    - contents: |
        # Managed by Salt (monitoring.otelcol). Logs are forwarded to Sentry.
        [Journal]
        SystemMaxUse=200M
        MaxRetentionSec=3day
    - require:
      - file: /etc/systemd/journald.conf.d

systemd-journald:
  service.running:
    - watch:
      - file: /etc/systemd/journald.conf.d/90-sentry-retention.conf
