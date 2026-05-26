redis_exporter_pkg:
  pkg.installed:
    - name: prometheus-redis-exporter

prometheus-redis-exporter:
  service.running:
    - enable: True
    - require:
      - pkg: redis_exporter_pkg