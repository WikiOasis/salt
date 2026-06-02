opensearch_exporter_pkg:
  pkg.installed:
    - name: prometheus-elasticsearch-exporter

/etc/default/prometheus-elasticsearch-exporter:
  file.managed:
    - contents: |
        ARGS="--es.uri=http://localhost:9200"
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: opensearch_exporter_pkg

prometheus-elasticsearch-exporter:
  service.running:
    - enable: True
    - watch:
      - file: /etc/default/prometheus-elasticsearch-exporter
    - require:
      - pkg: opensearch_exporter_pkg