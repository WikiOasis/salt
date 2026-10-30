{%- set exporter = salt['pillar.get']('redis:exporter', {}) %}
{%- set args = [] %}
{%- if exporter.get('check_keys') %}
{%- do args.append('--check-keys=' ~ exporter.check_keys | join(',')) %}
{%- endif %}

redis_exporter_pkg:
  pkg.installed:
    - name: prometheus-redis-exporter

/etc/default/prometheus-redis-exporter:
  file.managed:
    - contents: |
        ARGS="{{ args | join(' ') }}"
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: redis_exporter_pkg

prometheus-redis-exporter:
  service.running:
    - enable: True
    - watch:
      - file: /etc/default/prometheus-redis-exporter
    - require:
      - pkg: redis_exporter_pkg
