{%- set password = salt['pillar.get']('monitoring:mysqld_exporter_password') %}

mysqld_exporter_pkg:
  pkg.installed:
    - name: prometheus-mysqld-exporter

/etc/prometheus:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'
    - makedirs: True

/etc/prometheus/mysqld.my.cnf:
  file.managed:
    - contents: |
        [client]
        user     = prom_exporter
        password = {{ password }}
        host     = 127.0.0.1
        port     = 3306
    - user: root
    - group: prometheus
    - mode: '0640'
    - require:
      - pkg: mysqld_exporter_pkg
      - file: /etc/prometheus

/etc/default/prometheus-mysqld-exporter:
  file.managed:
    - contents: |
        ARGS="--config.my-cnf=/etc/prometheus/mysqld.my.cnf"
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: mysqld_exporter_pkg

prometheus-mysqld-exporter:
  service.running:
    - enable: True
    - watch:
      - file: /etc/prometheus/mysqld.my.cnf
      - file: /etc/default/prometheus-mysqld-exporter
    - require:
      - pkg: mysqld_exporter_pkg