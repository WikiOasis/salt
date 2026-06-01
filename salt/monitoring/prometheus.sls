{%- set retention = salt['pillar.get']('monitoring:prometheus:retention', '15d') %}

prometheus_package:
  pkg.installed:
    - name: prometheus

/etc/default/prometheus:
  file.managed:
    - contents: |
        ARGS="--storage.tsdb.retention.time={{ retention }} --web.enable-lifecycle"
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: prometheus_package
    - watch_in:
      - service: prometheus

/etc/prometheus/prometheus.yml:
  file.managed:
    - source: salt://monitoring/files/prometheus/prometheus.yml.jinja
    - template: jinja
    - user: root
    - group: prometheus
    - mode: '0640'
    - require:
      - pkg: prometheus_package
    - watch_in:
      - service: prometheus

/etc/prometheus/file_sd:
  file.directory:
    - user: prometheus
    - group: prometheus
    - mode: '0755'
    - makedirs: True
    - require:
      - pkg: prometheus_package

# One JSON target file per exporter type; Prometheus watches this directory
# via file_sd_configs and auto-reloads when files change (refresh_interval: 5m).
# Adding a host to dns_hosts pillar and re-applying this state is all that is
# needed to register it as a new scrape target.
{%- for job, prefix, port in [
    ('node',       None,          9100),
    ('mysqld',     'db',          9104),
    ('haproxy',    'proxy',       9101),
    ('redis',      'redis',       9121),
    ('statsd',     'monitoring',  9102),
    ('phpfpm',     'apps/mw',     9253),
    ('opensearch', 'opensearch',  9114),
] %}
/etc/prometheus/file_sd/{{ job }}.json:
  file.managed:
    - source: salt://monitoring/files/prometheus/file_sd/{{ job }}.json.jinja
    - template: jinja
    - user: prometheus
    - group: prometheus
    - mode: '0640'
    - require:
      - file: /etc/prometheus/file_sd
{%- endfor %}

prometheus:
  service.running:
    - enable: True
    - watch:
      - file: /etc/prometheus/prometheus.yml
      - file: /etc/default/prometheus
{%- for job in ['node', 'mysqld', 'haproxy', 'redis', 'statsd', 'phpfpm', 'opensearch'] %}
      - file: /etc/prometheus/file_sd/{{ job }}.json
{%- endfor %}
    - require:
      - pkg: prometheus_package
      - file: /etc/prometheus/file_sd