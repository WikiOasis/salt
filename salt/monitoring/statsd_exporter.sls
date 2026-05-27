prometheus_user:
  user.present:
    - name: prometheus
    - system: True
    - shell: /usr/sbin/nologin
    - home: /var/lib/prometheus
    - createhome: False

statsd_exporter_binary:
  archive.extracted:
    - name: /opt/statsd_exporter
    - source: https://github.com/prometheus/statsd_exporter/releases/download/v0.28.0/statsd_exporter-0.28.0.linux-amd64.tar.gz
    - source_hash: https://github.com/prometheus/statsd_exporter/releases/download/v0.28.0/sha256sums.txt
    - archive_format: tar
    - options: '--strip-components=1'
    - enforce_toplevel: False
    - if_missing: /opt/statsd_exporter/statsd_exporter

/usr/local/bin/prometheus-statsd-exporter:
  file.symlink:
    - target: /opt/statsd_exporter/statsd_exporter
    - require:
      - archive: statsd_exporter_binary

/etc/systemd/system/prometheus-statsd-exporter.service:
  file.managed:
    - contents: |
        [Unit]
        Description=Prometheus StatsD Exporter
        After=network.target

        [Service]
        User=prometheus
        ExecStart=/usr/local/bin/prometheus-statsd-exporter
        Restart=on-failure

        [Install]
        WantedBy=multi-user.target
    - user: root
    - group: root
    - mode: '0644'

prometheus-statsd-exporter:
  service.running:
    - enable: True
    - require:
      - user: prometheus_user
      - file: /usr/local/bin/prometheus-statsd-exporter
      - file: /etc/systemd/system/prometheus-statsd-exporter.service