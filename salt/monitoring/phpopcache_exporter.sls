{%- set cfg = salt['pillar.get']('php', {}) %}
{%- set version = cfg.get('version', '8.3') %}
{%- set socket = '/run/php/php' ~ version ~ '-fpm.sock' %}

phpopcache_exporter_binary:
  archive.extracted:
    - name: /opt/phpopcache_exporter
    - source: https://github.com/Lusitaniae/phpfpm_exporter/releases/download/v0.6.0/phpfpm_exporter-0.6.0.linux-amd64.tar.gz
    - source_hash: sha256=1d1e19afdadb0a40840e0212beb83d67dec4a74d77e9cfb27c4bb33bf652ca3f
    - archive_format: tar
    - enforce_toplevel: False
    - if_missing: /opt/phpopcache_exporter/phpfpm_exporter-0.6.0.linux-amd64/phpfpm_exporter

/usr/local/bin/prometheus-phpopcache-exporter:
  file.symlink:
    - target: /opt/phpopcache_exporter/phpfpm_exporter-0.6.0.linux-amd64/phpfpm_exporter
    - require:
      - archive: phpopcache_exporter_binary

/opt/phpopcache_exporter/opcache_status.php:
  file.managed:
    - source: salt://monitoring/files/php/opcache_status.php
    - user: www-data
    - group: www-data
    - mode: '0644'
    - makedirs: True
    - require:
      - archive: phpopcache_exporter_binary

/etc/systemd/system/prometheus-phpopcache-exporter.service:
  file.managed:
    - contents: |
        [Unit]
        Description=Prometheus PHP OPcache Exporter
        After=network.target php{{ version }}-fpm.service

        [Service]
        User=www-data
        ExecStart=/usr/local/bin/prometheus-phpopcache-exporter \
          --web.listen-address ":9254" \
          --phpfpm.socket-paths "{{ socket }}" \
          --phpfpm.script-collector-paths "/opt/phpopcache_exporter/opcache_status.php"
        Restart=on-failure

        [Install]
        WantedBy=multi-user.target
    - user: root
    - group: root
    - mode: '0644'

prometheus-phpopcache-exporter:
  service.running:
    - enable: True
    - watch:
      - file: /etc/systemd/system/prometheus-phpopcache-exporter.service
      - file: /usr/local/bin/prometheus-phpopcache-exporter
      - file: /opt/phpopcache_exporter/opcache_status.php
