haproxy_exporter_pkg:
  pkg.installed:
    - name: prometheus-haproxy-exporter

# prometheus-haproxy-exporter runs as the 'prometheus' user; it needs
# read access to the haproxy stats socket (mode 660, group haproxy).
prometheus_in_haproxy_group:
  user.present:
    - name: prometheus
    - groups:
      - haproxy
    - remove_groups: False
    - require:
      - pkg: haproxy_exporter_pkg

/etc/default/prometheus-haproxy-exporter:
  file.managed:
    - contents: |
        ARGS="--haproxy.scrape-uri=unix:/run/haproxy/admin.sock"
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: haproxy_exporter_pkg

prometheus-haproxy-exporter:
  service.running:
    - enable: True
    - watch:
      - file: /etc/default/prometheus-haproxy-exporter
    - require:
      - pkg: haproxy_exporter_pkg
      - user: prometheus_in_haproxy_group
