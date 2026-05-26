statsd_exporter_pkg:
  pkg.installed:
    - name: prometheus-statsd-exporter

prometheus-statsd-exporter:
  service.running:
    - enable: True
    - require:
      - pkg: statsd_exporter_pkg