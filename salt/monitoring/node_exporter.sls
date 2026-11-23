{%- set bind = (salt['network.ip_addrs'](cidr='10.0.0.0/8') or ['127.0.0.1'])[0] %}

node_exporter_pkg:
  pkg.installed:
    - name: prometheus-node-exporter

# Listen on the vRack address only; Prometheus scrapes it over 10.0.0.0/8.
/etc/default/prometheus-node-exporter:
  file.managed:
    - contents: |
        ARGS="--web.listen-address={{ bind }}:9100"
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: node_exporter_pkg

prometheus-node-exporter:
  service.running:
    - enable: True
    - watch:
      - file: /etc/default/prometheus-node-exporter
    - require:
      - pkg: node_exporter_pkg
