{%- set cfg = salt['pillar.get']('php', {}) %}
{%- set version = cfg.get('version', '8.3') %}
{%- set socket = '/run/php/php' ~ version ~ '-fpm.sock' %}

phpfpm_exporter_binary:
  archive.extracted:
    - name: /opt/phpfpm_exporter
    - source: https://github.com/hipages/php-fpm_exporter/releases/download/v2.2.0/php-fpm_exporter_2.2.0_linux_amd64.tar.gz
    - source_hash: sha256=b1c207fcd89f9be20104fd90bc76b3c584987ea5a769c99d5759f79af8322449
    - archive_format: tar
    - enforce_toplevel: False
    - if_missing: /opt/phpfpm_exporter/php-fpm_exporter

/usr/local/bin/prometheus-phpfpm-exporter:
  file.symlink:
    - target: /opt/phpfpm_exporter/php-fpm_exporter
    - require:
      - archive: phpfpm_exporter_binary

/etc/systemd/system/prometheus-phpfpm-exporter.service:
  file.managed:
    - contents: |
        [Unit]
        Description=Prometheus PHP-FPM Exporter
        After=network.target php{{ version }}-fpm.service

        [Service]
        User=www-data
        ExecStart=/usr/local/bin/prometheus-phpfpm-exporter server \
          --phpfpm.fix-process-count \
          --phpfpm.scrape-uri "unix://{{ socket }};/status"
        Restart=on-failure

        [Install]
        WantedBy=multi-user.target
    - user: root
    - group: root
    - mode: '0644'

prometheus-phpfpm-exporter:
  service.running:
    - enable: True
    - watch:
      - file: /etc/systemd/system/prometheus-phpfpm-exporter.service
      - file: /usr/local/bin/prometheus-phpfpm-exporter
