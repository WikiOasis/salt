{%- set retention = salt['pillar.get']('monitoring:prometheus:retention', '15d') %}

{#- One entry per scrape job: (job name, dns_hosts prefix, exporter port). The
    prefix and port are documentation here -- each job's own
    file_sd/<job>.json.jinja hardcodes them -- but the job names drive both the
    target files written below and the watch list on the service, so a job
    added here is scraped and reloads Prometheus without a second edit. The
    matching scrape_configs stanza still has to be added to
    files/prometheus/prometheus.yml.jinja by hand. #}
{%- set jobs = [
    ('node',       None,          9100),
    ('mysqld',     'db',          9104),
    ('haproxy',    'proxy',       9101),
    ('redis',      'redis',       9121),
    ('statsd',     'monitoring',  9102),
    ('phpfpm',     'apps/mw',     9253),
    ('phpopcache', 'apps/mw/task', 9254),
    ('opensearch', 'opensearch',  9114),
    ('cloudflare', 'monitoring',  9199),
    ('authentik',  'auth',        9300),
] %}

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
{%- for job, prefix, port in jobs %}
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
{%- for job, prefix, port in jobs %}
      - file: /etc/prometheus/file_sd/{{ job }}.json
{%- endfor %}
    - require:
      - pkg: prometheus_package
      - file: /etc/prometheus/file_sd